"""Handlers PTB v21: mensajes, joins, reacciones, my_chat_member."""
from __future__ import annotations

import asyncio
import html as _h
import logging
import time
from collections import deque

import aiohttp
from telegram import (
    ChatMemberUpdated,
    Update,
)
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import borrado_diferido
from . import antiraid
from . import desofuscar
from . import link_reader
from . import admin_report, gentle_warning, greetings, learning, notify_prefs, quips, rule_explain, story_reader, trust as _trust, user_signals, verification
from .config import Config
from .db import DB
from .detectors import Hit
from .i18n import t
from .detectors import cas as cas_det
from .detectors import external_mention as ext_det
from .detectors import first_msg_media as media_det
from .detectors import story_share as story_det
from .detectors import forward_first_msg as fwd_det
from .detectors import inline_buttons as buttons_det
from .detectors import commercial_ad as comad_det
from .detectors import investment_scam as invscam_det
from .detectors import contact_spam as contact_det
from .detectors import cross_post as crosspost_det
from .detectors import external_reply as extreply_det
from .detectors import photos_batch as photos_batch_det
from .detectors import bio_spam as bio_spam_det
from .detectors import personal_channel as personal_channel_det
from .detectors import dormant_bot_mention as dormant_bot_det
from .detectors import emoji_only as emoji_only_det
from .detectors import jfm_delta as jfm_det
from .detectors import link_target as link_target_det
from .detectors import offplatform_contact as offplat_det
from .detectors import lols_bot as lols_det
from .detectors import premium_new_link as premium_det
from .detectors import reaction_farming as react_det
from .detectors import tg_deeplink as tgdeep_det
from .detectors import unicode_script as script_det
from .detectors import url_blocklist as url_det
from .federation import federate_ban
from .notifier import Notifier
from .scoring import Decision, decide

log = logging.getLogger(__name__)

# Con money_guard='soft' un hit de dinero/trabajo solo sobrevive si es MUY claro.
# El umbral de los detectores es 60; aquí exigimos bastante más para que solo caigan
# los casos evidentes y los borderline (trabajo/dinero legítimo dudoso) pasen.
_MONEY_SOFT_MIN_SCORE = 100


def _chat_allowed_scripts(db: DB, chat_id: int, cfg) -> list[str]:
    """Alfabetos permitidos en este chat, cayendo a ALLOWED_SCRIPTS del .env.

    `chat_settings.allowed_scripts` guarda un CSV ('latin,cyrillic') y su NULL
    significa «no se ha decidido aquí» → manda el .env. Esa herencia es lo que
    permite que una instalación que ya permitía cirílico no empiece a marcar a sus
    usuarios al actualizar.

    Ante cualquier problema de lectura se cae al .env: quedarse sin lista sería
    peor que usar la global, porque una lista vacía marca CUALQUIER alfabeto.
    """
    try:
        s = db.get_chat_settings(chat_id)
        crudo = (s["allowed_scripts"] if s is not None else None) or ""
    except Exception:  # noqa: BLE001 — chat sin settings, columna vieja, BD ocupada
        return list(cfg.allowed_scripts)
    propios = [x.strip().lower() for x in crudo.split(",") if x.strip()]
    return propios or list(cfg.allowed_scripts)


def _chat_money_guard(db: DB, chat_id: int) -> str:
    """Modo money_guard del chat: 'normal' | 'soft' | 'off'. A prueba de fallos."""
    try:
        s = db.get_chat_settings(chat_id)
        return (s["money_guard"] if s is not None else None) or "normal"
    except Exception:  # noqa: BLE001 — chat sin settings, columna vieja, BD ocupada
        return "normal"


def _apply_money_guard(hit: Hit, mode: str) -> Hit:
    """Modula un hit de commercial_ad/investment_scam según el ajuste del chat.

    'normal' lo deja igual; 'off' lo anula; 'soft' solo lo conserva si el score es
    muy alto (caso claro), dejando pasar los borderline. Nunca sube la agresividad.
    """
    if not hit or mode == "normal":
        return hit
    if mode == "off":
        return Hit.none()
    if mode == "soft" and hit.score < _MONEY_SOFT_MIN_SCORE:
        return Hit.none()
    return hit


def permisos_perdidos(old, new) -> list[str]:
    """Qué podía hacer el bot y ya no, sin haber salido del grupo.

    Se compara ANTES contra DESPUÉS en vez de mirar solo el estado nuevo, porque lo
    que hay que avisar es el CAMBIO: un bot que nunca fue admin en un grupo no debe
    generar un aviso cada vez que alguien toca cualquier otra cosa del chat.
    """
    dentro = ("member", "restricted", "administrator", "creator", "owner")
    if new is None or getattr(new, "status", None) not in dentro:
        return []                      # ya no está dentro: de eso avisa el otro aviso
    if old is None or getattr(old, "status", None) not in dentro:
        return []                      # acaba de entrar, no ha perdido nada
    perdidos: list[str] = []
    era_admin = getattr(old, "status", None) in ("administrator", "creator", "owner")
    es_admin = getattr(new, "status", None) in ("administrator", "creator", "owner")
    if era_admin and not es_admin:
        return ["admin"]               # lo engloba todo, no hace falta detallar más
    if _can_delete(old) and not _can_delete(new):
        perdidos.append("borrar")
    if _can_restrict(old) and not _can_restrict(new):
        perdidos.append("restringir")
    return perdidos


async def _avisar_si_le_recortan(context, db: DB, cfg: Config, chat, old, new, actor) -> None:
    perdidos = permisos_perdidos(old, new)
    if not perdidos:
        return
    log.warning("permisos recortados en chat=%s (%s): %s", chat.id, chat.title, perdidos)
    if not cfg.admin_notify_chat_id or not notify_prefs.effective(db, "bot_demoted", cfg):
        return
    actor_label = "?"
    if actor is not None:
        actor_label = f"@{actor.username}" if actor.username else (actor.first_name or str(actor.id))
    from telegram import InlineKeyboardMarkup
    try:
        await context.bot.send_message(
            chat_id=cfg.admin_notify_chat_id,
            text=t("hdl.bot_demoted",
                   chat=_h.escape(str(chat.title or chat.id)),
                   actor=_h.escape(str(actor_label)),
                   perdidos=" · ".join(t(f"hdl.bot_demoted.{p}") for p in perdidos)),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[notify_prefs.mute_button("bot_demoted")]]),
        )
    except TelegramError as exc:
        log.warning("aviso de permisos recortados fallo: %s", exc)


# Reglas de severidad máxima: ni el trust las degrada ni el modo suave las ablanda.
#
# `link_target_spam` entra aquí porque no es una heurística sobre el mensaje: es lo
# que el chat enlazado dice de sí mismo. Justo el caso que el trust dejaba escapar
# (cuenta veterana, probablemente robada, publicando un canal de packs): con el
# atajo por trust alto el enlace se quedaba en el grupo.
HARD_RULES_BAN = frozenset({
    "cas_match", "lols_match", "federation_known_ban", "reaction_farming",
    "link_target_spam",
})


def _modo_suave(db: DB, chat_id: int, cfg) -> bool:
    """¿Este chat silencia en vez de expulsar? NULL en la columna = hereda el .env."""
    try:
        s = db.get_chat_settings(chat_id)
        v = s["soft_ban"] if s is not None else None
    except Exception:  # noqa: BLE001 — chat sin settings, columna vieja, BD ocupada
        return bool(getattr(cfg, "soft_ban", False))
    if v is None:
        return bool(getattr(cfg, "soft_ban", False))
    return bool(v)


def _enlaces_tg_de(hits: list[Hit]) -> list[str]:
    """URLs t.me que ya han disparado un hit, para ir a mirar a dónde llevan.

    Se leen del payload de `external_mention_or_link` en vez de volver a recorrer
    el mensaje: así el destino solo se consulta cuando el enlace YA es sospechoso,
    y nunca por un t.me al propio grupo (que ese detector ya descarta).
    """
    urls: list[str] = []
    for hit in hits:
        for url in (hit.payload or {}).get("external_tg_links") or []:
            if url not in urls:
                urls.append(url)
    return urls


def _can_restrict(member) -> bool:
    if member.status == ChatMemberStatus.OWNER:
        return True
    if member.status == ChatMemberStatus.ADMINISTRATOR:
        return bool(getattr(member, "can_restrict_members", False))
    return False


def _can_delete(member) -> bool:
    if member.status == ChatMemberStatus.OWNER:
        return True
    if member.status == ChatMemberStatus.ADMINISTRATOR:
        return bool(getattr(member, "can_delete_messages", False))
    return False


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tracking de en qué chats está el bot y con qué permisos."""
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    cmu: ChatMemberUpdated = update.my_chat_member
    if not cmu:
        return
    chat = cmu.chat
    old = cmu.old_chat_member
    new = cmu.new_chat_member
    am_admin = new.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    db.upsert_bot_chat(
        chat_id=chat.id,
        title=chat.title,
        chat_type=chat.type,
        am_admin=am_admin,
        can_restrict=_can_restrict(new),
        can_delete=_can_delete(new),
        username=getattr(chat, "username", None),
    )
    log.info(
        "my_chat_member chat=%s (%s) status=%s admin=%s restrict=%s delete=%s",
        chat.id, chat.title, new.status, am_admin, _can_restrict(new), _can_delete(new),
    )

    # Aviso si le QUITAN PERMISOS sin echarlo. Es el fallo silencioso: el bot se
    # queda dentro, sale como siempre en `/chats`, sigue detectando el spam... y no
    # puede tocarlo. Sin este aviso no te enteras hasta que se cuela algo.
    await _avisar_si_le_recortan(context, db, cfg, chat, old, new, cmu.from_user)

    # Aviso si EXPULSAN al bot de un grupo (estaba dentro y ahora está fuera).
    # Activo por defecto, configurable con NOTIFY_BOT_REMOVED.
    old_status = old.status if old else None
    was_in = old_status in (
        ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED,
        ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER,
    )
    now_out = new.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
    removed_default = cfg.notify_bot_removed and bool(cfg.admin_notify_chat_id)
    if was_in and now_out and notify_prefs.is_enabled(db, "bot_removed", removed_default):
        actor = cmu.from_user
        actor_label = "?"
        if actor:
            actor_label = f"@{actor.username}" if actor.username else (actor.first_name or str(actor.id))
        verbo = t("hdl.bot_removed.verb_banned") if new.status == ChatMemberStatus.BANNED else t("hdl.bot_removed.verb_kicked")
        from telegram import InlineKeyboardMarkup
        try:
            await context.bot.send_message(
                chat_id=cfg.admin_notify_chat_id,
                text=t(
                    "hdl.bot_removed_alert",
                    verb=verbo,
                    chat=_h.escape(chat.title or str(chat.id)),
                    chat_id=chat.id,
                    actor=_h.escape(actor_label),
                    actor_id=(f" (<code>{actor.id}</code>)" if actor else ""),
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[notify_prefs.mute_button("bot_removed")]]),
            )
        except TelegramError as exc:
            log.debug("aviso bot expulsado fallo: %s", exc)


async def _ban_join_direct(context, db, cfg, cmu, user, *, score, rule, reason, payload=None):
    """Ban directo en el JOIN (perfil/bio/fotos spam). Centraliza el Decision +
    _apply_action que se repetía en obvious_spam/bio_spam/photos_batch."""
    decision = Decision(
        action="ban", score=score, rule=rule, reason=reason, payload=payload or {},
    )
    await _apply_action(
        context, db, cfg, chat_id=cmu.chat.id, chat_title=cmu.chat.title,
        user_id=user.id, username=user.username, message_id=None,
        decision=decision, original_text=None, first_name=user.first_name,
    )


def _is_admin_ban_or_kick(
    old_status: str | None,
    new_status: str | None,
    actor_id: int | None,
    target_id: int,
    bot_id: int,
) -> bool:
    """True si el cambio de membresía es un ban/kick hecho por OTRO admin (no el bot).

    Distingue lo que el evento ChatMemberUpdated NO separa por sí solo:
      - →BANNED: siempre acción de un admin.
      - →LEFT: puede ser self-leave (el usuario se va solo: actor == afectado) o
        kick por un admin (actor != afectado). Solo el kick cuenta.
    Excluye acciones del propio bot y casos sin actor conocido.
    """
    if actor_id is None or actor_id == bot_id:
        return False
    was_active = old_status in (
        ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED, ChatMemberStatus.ADMINISTRATOR,
    )
    if not was_active:
        return False
    if new_status == ChatMemberStatus.BANNED:
        return True
    if new_status == ChatMemberStatus.LEFT and actor_id != target_id:
        return True
    return False


def _is_join(old_status: str | None, new_status: str | None, new_is_member: bool | None) -> bool:
    """True si el evento representa una ENTRADA al grupo.

    Cubre el join normal (→MEMBER) y el join que aterriza directo en RESTRICTED
    con is_member=True (otro bot/admin lo mutea en el mismo instante del join, o
    grupos que restringen al recién llegado). Sin esto, ese usuario se saltaría
    todo el pipeline de entrada (federación, CAS, lols, verificación).
    Excluye RESTRICTED→MEMBER (unmute, no es entrada) y RESTRICTED con
    is_member=False (restringido y fuera, no está dentro).
    """
    if old_status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, None):
        return False
    if new_status == ChatMemberStatus.MEMBER:
        return True
    if new_status == ChatMemberStatus.RESTRICTED and bool(new_is_member):
        return True
    return False


async def _check_admin_ban_abuse(context, db, cfg, cmu) -> None:
    """Registra el ban manual de un admin y, si supera el umbral en la ventana,
    avisa (con botón para DESHACER los baneos).

    LÍMITE de Telegram: el bot NO puede quitar permisos ni expulsar a un admin
    nombrado por el creador; solo detecta, avisa, y puede desbanear a los afectados.
    """
    actor = cmu.from_user
    if actor is None:
        return
    chat = cmu.chat
    admin_id = actor.id
    ts = cmu.date.timestamp() if cmu.date else time.time()
    db.record_admin_ban(chat.id, admin_id, cmu.new_chat_member.user.id, ts)

    since = ts - cfg.admin_ban_abuse_window_h * 3600
    bans = db.admin_bans_in_window(chat.id, admin_id, since)
    if len(bans) < cfg.admin_ban_abuse_threshold:
        return
    # Dedup: no re-avisar por el mismo admin/chat dentro de la ventana.
    dedup = context.bot_data.setdefault("_abuse_alerted", {})
    key = (chat.id, admin_id)
    now = time.time()
    if now - dedup.get(key, 0) < cfg.admin_ban_abuse_window_h * 3600:
        return
    dedup[key] = now
    if not cfg.admin_notify_chat_id:
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    n = len(bans)
    label = f"@{actor.username}" if actor.username else (actor.first_name or str(admin_id))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("hdl.btn.undo_unbans", n=n),
                              callback_data=f"abuse:undo:{chat.id}:{admin_id}:{int(since)}")],
        [InlineKeyboardButton(t("hdl.btn.ignore_legit"),
                              callback_data=f"abuse:ok:{chat.id}:{admin_id}")],
    ])
    text = t(
        "hdl.admin_abuse_alert",
        chat=_h.escape(chat.title or str(chat.id)),
        admin_id=admin_id,
        admin_label=_h.escape(label),
        n=n,
        hours=cfg.admin_ban_abuse_window_h,
    )
    try:
        await context.bot.send_message(
            chat_id=cfg.admin_notify_chat_id, text=text, parse_mode="HTML",
            reply_markup=kb, disable_web_page_preview=True,
        )
    except TelegramError as exc:
        log.debug("aviso abuse admin fallo: %s", exc)


async def on_abuse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Botones del aviso de abuse: deshacer (desbanear) o ignorar."""
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("abuse:"):
        return
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer(t("hdl.only_admin_decide"), show_alert=True)
        return
    parts = q.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "ok":
        await q.answer(t("hdl.marked_legit_toast"))
        try:
            await _quitar_botones(q)
        except TelegramError:
            pass
        return
    if action == "undo" and len(parts) == 5:
        chat_id, admin_id, since = int(parts[2]), int(parts[3]), float(parts[4])
        bans = db.admin_bans_in_window(chat_id, admin_id, since)
        ok = 0
        for r in bans:
            try:
                await context.bot.unban_chat_member(
                    chat_id=chat_id, user_id=r["target_id"], only_if_banned=True,
                )
                ok += 1
            except TelegramError:
                pass
        await q.answer(t("hdl.unbanned", ok=ok, total=len(bans)))
        try:
            base = q.message.text_html if q.message else ""
            await q.edit_message_text(
                base + f"\n\n↩️ <b>Deshecho:</b> {ok}/{len(bans)} usuarios desbaneados.",
                parse_mode="HTML",
            )
        except TelegramError:
            pass


async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detectar JOINs y BANS de usuarios al grupo."""
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    cmu: ChatMemberUpdated = update.chat_member
    if not cmu:
        return
    if not cfg.is_moderated(cmu.chat.id):
        return
    old_status = cmu.old_chat_member.status if cmu.old_chat_member else None
    new_status = cmu.new_chat_member.status

    # Detección de ban/kick realizado por OTRO admin (no por el bot). Ver
    # _is_admin_ban_or_kick: separa self-leave (se va solo) de kick por admin.
    # READMISIÓN de alguien que TÚ tenías baneado en la federación. Otro admin del
    # grupo puede levantar el ban desde la app de Telegram, y hasta ahora el bot no
    # miraba esa transición: solo vigilaba las que van HACIA ban o expulsión. Caso
    # real: un usuario baneado el 2-ago apareció readmitido y silenciado en uno de
    # los tres grupos, siguió escribiendo día y medio, y nadie se enteró.
    #
    # Se vuelve a aplicar el ban (una lista federada que otro puede deshacer en
    # silencio no sirve de nada) y se AVISA, con un botón para aceptar la decisión
    # del otro admin si te parece bien. Sin el aviso sería una guerra invisible.
    _readmitido = (
        old_status == ChatMemberStatus.BANNED
        and new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED)
        and cmu.from_user is not None and cmu.from_user.id != context.bot.id
    )
    if _readmitido and db.is_banned(cmu.new_chat_member.user.id):
        objetivo = cmu.new_chat_member.user
        log.warning("READMITIDO un baneado: user=%s chat=%s por actor=%s → re-ban",
                    objetivo.id, cmu.chat.id, cmu.from_user.id)
        if not cfg.shadow:
            try:
                await context.bot.ban_chat_member(chat_id=cmu.chat.id, user_id=objetivo.id)
            except TelegramError as exc:
                log.warning("no se pudo re-banear al readmitido %s: %s", objetivo.id, exc)
        db.log_action(
            chat_id=cmu.chat.id, user_id=objetivo.id, username=objetivo.username,
            message_id=0, rule="federation_known_ban", action="ban", score=0,
            mode=("shadow" if cfg.shadow else "active"),
            payload={"via": "readmision", "actor": cmu.from_user.id},
        )
        await _avisar_readmision(context, cfg, cmu, objetivo)
        return

    if _is_admin_ban_or_kick(
        old_status, new_status,
        actor_id=cmu.from_user.id if cmu.from_user else None,
        target_id=cmu.new_chat_member.user.id,
        bot_id=context.bot.id,
    ):
        await _notify_manual_ban(context, db, cmu)
        # Un admin baneando desde la propia app de Telegram no pasa por ningún
        # comando del bot, así que este era el único camino de ban que dejaba la
        # bienvenida huérfana en el grupo. Solo en BAN: a un kick puede seguirle
        # una reentrada legítima, y ahí borrar el saludo no aporta nada.
        if new_status == ChatMemberStatus.BANNED:
            try:
                await verification.limpiar_bienvenidas(
                    context, db, cmu.new_chat_member.user.id)
            except Exception as exc:  # noqa: BLE001
                log.debug("limpieza de bienvenida tras ban manual falló: %s", exc)
        # Anti-abuse: solo cuenta los BANEOS (no kicks). Si un admin banea a muchos
        # en poco tiempo, avisa para revisar (con botón para deshacer los baneos).
        if new_status == ChatMemberStatus.BANNED and cfg.admin_ban_abuse_enabled:
            await _check_admin_ban_abuse(context, db, cfg, cmu)

    if not _is_join(
        old_status, new_status,
        getattr(cmu.new_chat_member, "is_member", None),
    ):
        return
    user = cmu.new_chat_member.user
    # join_ts = hora REAL del evento de Telegram (cmu.date), no la de proceso:
    # si el bot procesa el join con retraso, usar time.time() inflaría la rapidez
    # aparente del primer mensaje (falso positivo de jfm_delta, caso Yorscluni).
    join_epoch = cmu.date.timestamp() if cmu.date else None
    db.record_join(cmu.chat.id, user.id, user.username, join_ts=join_epoch)
    db.remember_username(user.username, user.id)

    # ¿Está entrando una avalancha? Todo lo demás en el bot razona persona a
    # persona, y contra una raid eso no vale: el ataque no está en ninguna cuenta,
    # está en el conjunto. Ver `antiraid.py`. NO se cierra el grupo ni se silencia
    # a nadie por entrar; solo se endurecen los umbrales de quien llega ahora.
    if antiraid.registrar_entrada(context, cmu.chat.id, join_epoch):
        log.warning("antiraid: avalancha de entradas en chat=%s (%s)", cmu.chat.id, cmu.chat.title)
        await antiraid.avisar(context, cfg, cmu.chat.id, cmu.chat.title)

    if db.is_banned(user.id):
        log.info("Usuario %s reentra estando baneado en federación → ban local", user.id)
        await _apply_action(
            context, db, cfg, chat_id=cmu.chat.id, chat_title=cmu.chat.title,
            user_id=user.id, username=user.username, message_id=None,
            decision=Decision(action="ban", score=999, rule="federation_known_ban",
                               reason=t("reason.federation_rejoin"), payload={}),
            original_text=None, first_name=user.first_name,
        )
        return

    # NUEVO: bot añadido al grupo. Los bots no pulsan SOY HUMANO y los spam-bots
    # postean porno/promo. Auto-kick + aviso al admin (los bots legítimos los
    # añade el admin, que puede re-añadirlos; mejor pecar de cauto).
    if user.is_bot and user.id != context.bot.id:
        added_by = cmu.from_user
        log.info("Bot añadido user=%s (@%s) chat=%s por %s → kick + aviso",
                 user.id, user.username, cmu.chat.id, added_by.id if added_by else "?")
        # En shadow no expulsamos (contrato: sin acciones reales); el aviso al
        # admin sí se manda, es informativo.
        if not cfg.shadow:
            try:
                await context.bot.ban_chat_member(chat_id=cmu.chat.id, user_id=user.id)
                await asyncio.sleep(0.3)
                await context.bot.unban_chat_member(chat_id=cmu.chat.id, user_id=user.id, only_if_banned=True)
            except TelegramError as exc:
                log.warning("auto-kick bot fallo: %s", exc)
        if cfg.admin_notify_chat_id:
            who = (f'@{added_by.username}' if added_by and added_by.username
                   else (added_by.first_name if added_by else "?"))
            try:
                await context.bot.send_message(
                    chat_id=cfg.admin_notify_chat_id,
                    text=t(
                        "hdl.bot_added_kicked",
                        chat=cmu.chat.title or cmu.chat.id,
                        bot_username=user.username or "?",
                        bot_id=user.id,
                        adder=_h.escape(who),
                        adder_id=(f" (<code>{added_by.id}</code>)" if added_by else ""),
                    ),
                    parse_mode="HTML", disable_web_page_preview=True,
                )
            except TelegramError:
                pass
        return

    # Trust score precalculado: si el user reentró tras salir, puede tener
    # historial alto. Lo usamos para saltar la verificación y para no
    # autobanear ciegamente por CAS/lols si es claramente veterano.
    rejoin_trust = _trust_score_cached(context, db, cmu.chat.id, user.id)

    # NUEVO: detección de perfil OBVIAMENTE spammer (≥2 campos en script no-latín,
    # o 1 campo con ratio ≥0.7). Ban directo sin esperar a verificación ni primer
    # mensaje. Solo si NO es veterano (trust<70).
    if rejoin_trust < 70:
        # Mute provisional INMEDIATO: cierra la ventana en la que un recién
        # llegado podría escribir mientras corremos el análisis lento de perfil
        # (bio/fotos via Telethon + CAS/lols por red, que tardan segundos). Sin
        # esto, el botón SOY HUMANO no sirve: el user escribe antes de que lo
        # muteemos. Si resulta ban → ya queda fuera; si el perfil es legítimo →
        # verification.on_join lo desmutea al mandar el welcome amistoso.
        # En modo shadow NO muteamos (contrato: shadow no ejecuta acciones reales);
        # además, sin este guard el usuario quedaría muteado para siempre porque
        # verification.on_join retorna temprano en shadow sin desmutear.
        if not cfg.shadow:
            try:
                await context.bot.restrict_chat_member(
                    chat_id=cmu.chat.id, user_id=user.id,
                    permissions=verification.MUTED_PERMISSIONS,
                )
            except TelegramError as exc:
                log.debug("mute provisional fallo user=%s: %s", user.id, exc)
        sig_pre = None
        reporter_pre = context.bot_data.get("reporter")
        client_pre = reporter_pre.get_client() if reporter_pre else None
        if client_pre is not None:
            try:
                sig_pre = await user_signals.fetch(client_pre, user.id, chat_id=cmu.chat.id, first_name=user.first_name)
            except Exception as exc:  # noqa: BLE001
                log.debug("user_signals fetch user=%s exc: %s", user.id, exc)
        obvious_spam, obv_reasons = verification._is_obvious_spam_profile(
            sig_pre, user.username, user.first_name, user.last_name,
        )
        if obvious_spam:
            log.info(
                "OBVIOUS spam profile user=%s reasons=%s → ban directo",
                user.id, obv_reasons,
            )
            await _ban_join_direct(
                context, db, cfg, cmu, user, score=200, rule="obvious_spam_profile",
                reason=t("alert.obvious_spam") + " | ".join(
                    verification.render_reason_list(obv_reasons)[:3]),
                payload={"reasons": obv_reasons},
            )
            return

        # Nombre con ideogramas Han que SOLO se libra por el salvoconducto de
        # «cuenta antigua con foto». No se banea (podría ser un chino-hablante
        # real) pero tampoco se le deja pasar por la verificación de botón, que un
        # bot pulsa en tres segundos: se queda MUDO con el mute provisional ya
        # aplicado y decide el admin desde su privado. Caso medido: entró así,
        # se verificó en 3 s y soltó spam dos días después.
        if not cfg.shadow and verification.han_requiere_decision(
                sig_pre, user.username, user.first_name, user.last_name):
            log.info("HAN con salvoconducto user=%s chat=%s → mudo a la espera del admin",
                     user.id, cmu.chat.id)
            db.log_action(
                chat_id=cmu.chat.id, user_id=user.id, username=user.username,
                message_id=0, rule="han_pending_review", action="mute", score=0,
                mode="active", payload={"motivo": "nombre en Han + cuenta antigua con foto"},
            )
            await verification.avisar_han_mudo(context, db, cfg, cmu.chat, user, sig_pre)
            return

        # NUEVO: bio del perfil con señales claras de spam (invite link + emojis
        # sexuales + idioma extranjero + keywords). Caso real: bio alemán con
        # t.me/+ y emojis 🔥🥵. Aprovecha sig_pre ya cargado.
        if sig_pre is not None and sig_pre.bio:
            bio_hit = bio_spam_det.check(sig_pre.bio)
            if bio_hit:
                log.info(
                    "bio_spam user=%s score=%d → ban directo: %s",
                    user.id, bio_hit.score, bio_hit.reason[:200],
                )
                await _ban_join_direct(
                    context, db, cfg, cmu, user, score=bio_hit.score,
                    rule=bio_hit.rule, reason=bio_hit.reason, payload=bio_hit.payload,
                )
                return

        # NUEVO: el canal enlazado en el perfil usado como escaparate de spam.
        # Caso real: cuenta «Matthew», nombre latino, sin foto, sin username y con
        # la bio VACÍA (por eso pasó los filtros anteriores), con un canal chino
        # reclutando mulas de blanqueo. Aprovecha sig_pre: cero llamadas extra.
        # Solo dispara cuando hay varias señales a la vez (ver MIN_SCORE).
        if sig_pre is not None and sig_pre.personal_channel_title:
            try:
                pchan_hit = personal_channel_det.check(
                    sig_pre.personal_channel_title,
                    first_name=user.first_name, last_name=user.last_name,
                    username=user.username, allowed_scripts=_chat_allowed_scripts(db, cmu.chat.id, cfg),
                    has_photo=sig_pre.photo_count > 0, has_bio=bool(sig_pre.bio),
                    bio=sig_pre.bio,
                )
            except Exception as exc:  # noqa: BLE001
                # Mismo motivo que sus vecinos: el usuario YA tiene el mute
                # provisional puesto; una excepción aquí escaparía de
                # on_chat_member y lo dejaría muteado para siempre.
                log.debug("personal_channel check user=%s exc: %s", user.id, exc)
                pchan_hit = None
            if pchan_hit:
                log.info(
                    "personal_channel_spam user=%s score=%d canal=%r → ban directo",
                    user.id, pchan_hit.score, sig_pre.personal_channel_title[:60],
                )
                await _ban_join_direct(
                    context, db, cfg, cmu, user, score=pchan_hit.score,
                    rule=pchan_hit.rule, reason=pchan_hit.reason, payload=pchan_hit.payload,
                )
                return

        # NUEVO: fotos de perfil en ráfaga (≤2 min) → cuenta construida con
        # identidad robada. Caso real Javier (5 fotos en 18s). Ban directo.
        if client_pre is not None:
            # Protegido como su vecino user_signals.fetch: el usuario YA tiene el mute
            # provisional puesto arriba; si esto lanzara (foto sin date, respuesta rara
            # de Telethon...), la excepción escaparía de on_chat_member y lo dejaría
            # muteado para siempre y sin fila pendiente.
            try:
                photos_hit = await photos_batch_det.check(
                    client_pre, user.id, username=user.username,
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("photos_batch check user=%s exc: %s", user.id, exc)
                photos_hit = None
            if photos_hit:
                log.info(
                    "photos_batch_upload user=%s span=%.0fs n=%d → ban directo",
                    user.id, photos_hit.payload["span_seconds"], photos_hit.payload["n_photos"],
                )
                await _ban_join_direct(
                    context, db, cfg, cmu, user, score=photos_hit.score,
                    rule=photos_hit.rule, reason=photos_hit.reason, payload=photos_hit.payload,
                )
                return

    session: aiohttp.ClientSession = context.bot_data.get("http")
    # Lookup en lols.bot (complementario a CAS, gratis)
    if cfg.lols_enabled and session is not None:
        lols_hit = await lols_det.check(user.id, session)
        if lols_hit:
            # Veterano con trust muy alto + lols match = probable FP de lols.bot.
            # No autobaneamos: log + revisión humana via admin notif.
            if rejoin_trust >= 90:
                log.warning(
                    "lols_match user=%s trust=%d (veterano) → NO autoban, revisión humana",
                    user.id, rejoin_trust,
                )
                db.log_action(
                    chat_id=cmu.chat.id, user_id=user.id, username=user.username,
                    message_id=None, rule="lols_match_trusted_review", action="noop",
                    score=lols_hit.score, mode=cfg.mode,
                    payload={"trust": rejoin_trust, "would_be": "ban", "lols": lols_hit.payload},
                )
            else:
                decision = decide(
                    [lols_hit], cfg.ban_score, cfg.kick_score, cfg.mute_score,
                    cfg.first_msg_attack_action, is_first_msg_attack=False,
                )
                await _apply_action(
                    context, db, cfg, chat_id=cmu.chat.id, chat_title=cmu.chat.title,
                    user_id=user.id, username=user.username, message_id=None,
                    decision=decision, original_text=None, first_name=user.first_name,
                )
                return

    if cfg.cas_enabled and session is not None:
        hit = await cas_det.check(user.id, session, db, cfg.cas_cache_ttl_seconds)
        if hit:
            offenses = (hit.payload or {}).get("offenses", 0)
            if offenses >= cfg.cas_autoban_min and rejoin_trust >= 90:
                log.warning(
                    "cas_match user=%s offenses=%d trust=%d (veterano) → NO autoban, revisión humana",
                    user.id, offenses, rejoin_trust,
                )
                db.log_action(
                    chat_id=cmu.chat.id, user_id=user.id, username=user.username,
                    message_id=None, rule="cas_match_trusted_review", action="noop",
                    score=hit.score, mode=cfg.mode,
                    payload={"trust": rejoin_trust, "offenses": offenses, "would_be": "ban"},
                )
            elif offenses >= cfg.cas_autoban_min:
                decision = decide(
                    [hit], cfg.ban_score, cfg.kick_score, cfg.mute_score,
                    cfg.first_msg_attack_action, is_first_msg_attack=False,
                )
                await _apply_action(
                    context, db, cfg, chat_id=cmu.chat.id, chat_title=cmu.chat.title,
                    user_id=user.id, username=user.username, message_id=None,
                    decision=decision, original_text=None, first_name=user.first_name,
                )
                return
            else:
                # CAS=1 → no ban, solo log + notificación al admin
                db.log_action(
                    chat_id=cmu.chat.id, user_id=user.id, username=user.username,
                    message_id=None, rule="cas_low_offense", action="noop",
                    score=hit.score, mode=cfg.mode,
                    payload={"offenses": offenses, "reason": t("reason.cas_low_offense")},
                )
                log.info(
                    "CAS match user=%s offenses=%d < autoban_min=%d → revisión manual",
                    user.id, offenses, cfg.cas_autoban_min,
                )

    # Verification AL FINAL: si lols/cas no bannearon, ahora publicamos welcome
    # (con botón o amistoso según trust + perfil legítimo).
    if rejoin_trust < 70:
        # Pasamos sig_pre ya cargado para evitar segundo Telethon fetch
        await verification.on_join(
            update, context, cmu.chat, user, prefetched_sig=sig_pre,
        )
    else:
        log.info(
            "verification SKIP user=%s chat=%s: rejoin con trust=%d (veterano)",
            user.id, cmu.chat.id, rejoin_trust,
        )


async def _notify_manual_ban(
    context: ContextTypes.DEFAULT_TYPE,
    db: DB,
    cmu: ChatMemberUpdated,
) -> None:
    """Avisa al admin del bot cuando OTRO admin (no el bot) banea/expulsa a alguien.

    El aviso PRIMARIO va al DM directo del admin del bot (mismo sitio que el resto
    de alertas: revisiones, flood, borrados). Antes solo iba por el bot de notificaciones externo, así que
    no se veía si ese bot no estaba o el admin miraba el DM del propio bot.
    """
    cfg: Config = context.bot_data["cfg"]
    actor = cmu.from_user  # quien hizo el ban
    target = cmu.new_chat_member.user
    chat = cmu.chat

    actor_label = f"@{actor.username}" if actor.username else (actor.first_name or str(actor.id))
    target_label = f"@{target.username}" if target.username else (target.first_name or str(target.id))

    # Último mensaje conocido del baneado
    seen = db.get_seen(chat.id, target.id)
    last_msg_text = (seen["last_msg_text"] if seen else None) or t("hdl.no_messages_logged")
    last_msg_ts = seen["last_msg_ts"] if seen else None

    import datetime as _dt
    last_msg_when = ""
    if last_msg_ts:
        last_msg_when = " (" + _dt.datetime.fromtimestamp(last_msg_ts).strftime("%Y-%m-%d %H:%M") + ")"

    new_status_label = t(
        "hdl.manual_ban_status_ban"
        if cmu.new_chat_member.status == ChatMemberStatus.BANNED
        else "hdl.manual_ban_status_kick"
    )

    text = t(
        "hdl.manual_ban_alert",
        chat=_h.escape(chat.title or str(chat.id)),
        action=new_status_label,
        actor_id=actor.id,
        actor_label=_h.escape(actor_label),
        target_id=target.id,
        target_label=_h.escape(target_label),
        when=last_msg_when,
        last_msg=_h.escape(last_msg_text[:500]),
    )

    # 1) PRIMARIO: DM directo al admin del bot (donde recibe todo lo demás).
    # Silenciable en runtime (botón / /alertas); default activado.
    if cfg.admin_notify_chat_id and notify_prefs.is_enabled(db, "manual_ban", True):
        from telegram import InlineKeyboardMarkup
        try:
            await context.bot.send_message(
                chat_id=cfg.admin_notify_chat_id, text=text, parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[notify_prefs.mute_button("manual_ban")]]),
                disable_web_page_preview=True,
            )
        except TelegramError as exc:
            log.debug("manual_ban DM admin fallo: %s", exc)

    # 2) SECUNDARIO opcional: bot de notificaciones externo si está configurado.
    notifier = context.bot_data.get("notifier")
    session = context.bot_data.get("http")
    if notifier is not None and notifier.is_configured() and session is not None:
        try:
            await notifier.send_action_alert(
                session=session, action_id=0,
                chat_title=chat.title, chat_id=chat.id,
                user_id=target.id, username=target.username,
                action="manual_ban_external",
                rule=f"manual_ban_by_admin_{actor.id}",
                reason=t("reason.manual_ban_by_admin", admin=actor_label),
                score=0, original_text=last_msg_text, mode="active",
                federation_results=None,
            )
        except Exception:  # noqa: BLE001 — la notificación externa es secundaria, no debe romper
            pass
    log.info(
        "manual ban detected: actor=%s target=%s chat=%s",
        actor.id, target.id, chat.id,
    )


async def _ensure_chat_registered(context: ContextTypes.DEFAULT_TYPE, db: DB, chat) -> None:
    """Si vemos actividad en un chat no registrado todavía, verificamos los permisos del bot y lo registramos.

    Esto cubre el caso de updates 'descartados' al primer arranque o de chats
    donde el bot ya era admin antes de que el bot se levantara.
    """
    if chat.id in context.bot_data.setdefault("_chat_cache", set()):
        return
    try:
        me = await context.bot.get_chat_member(chat_id=chat.id, user_id=context.bot.id)
        am_admin = _can_restrict(me) or _can_delete(me) or getattr(me, "status", None) in ("administrator", "creator", "owner")
        db.upsert_bot_chat(
            chat_id=chat.id,
            title=getattr(chat, "title", None),
            chat_type=getattr(chat, "type", None),
            am_admin=am_admin,
            can_restrict=_can_restrict(me),
            can_delete=_can_delete(me),
            username=getattr(chat, "username", None),
        )
        context.bot_data["_chat_cache"].add(chat.id)
        log.info(
            "auto-registrado chat=%s (%s) admin=%s restrict=%s delete=%s",
            chat.id, getattr(chat, "title", None), am_admin, _can_restrict(me), _can_delete(me),
        )
    except TelegramError as exc:
        log.warning("auto-registro chat=%s falló: %s", chat.id, exc)


async def on_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-escanea mensajes editados (edit-attack: spammer edita a spam tras pasar filtros)."""
    cfg: Config = context.bot_data["cfg"]
    if not cfg.rescan_edited_messages:
        return
    # PTB v21: update.edited_message está disponible; reaprovechamos on_message.
    if update.edited_message:
        # Forzar que el flujo de on_message lo trate como mensaje nuevo
        # (Pasamos directamente; los detectores no diferencian)
        await on_message(update, context)


async def on_service_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Borra mensajes de servicio (X se unió, X salió, X cambió foto, etc.) si cleanservice=on."""
    msg = update.effective_message
    if not msg or not msg.chat:
        return
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    if cfg.shadow:
        return
    db.ensure_chat_settings(msg.chat_id)
    settings = db.get_chat_settings(msg.chat_id)
    if not settings or not settings["cleanservice"]:
        return
    try:
        await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
        log.debug("cleanservice delete chat=%s msg=%s", msg.chat_id, msg.message_id)
    except TelegramError as exc:
        log.debug("cleanservice fallo: %s", exc)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    msg = update.effective_message
    if msg is None:
        return
    if msg.from_user is None:
        # Mensaje "en nombre de un canal" (sender_chat): dentro se ignoran el post
        # auto-reenviado que encabeza los comentarios y los admins anónimos; un
        # canal externo comentando spam se banea con banChatSenderChat.
        await _moderate_channel_message(context, db, cfg, msg)
        return
    chat_id = msg.chat_id
    if msg.chat.type in ("group", "supergroup"):
        await _ensure_chat_registered(context, db, msg.chat)
    if not cfg.is_moderated(chat_id):
        return
    user = msg.from_user
    # Nuestro propio bot nunca se modera
    if user.id == context.bot.id:
        return
    # Bots EXTERNOS: ya NO se saltan. Un bot miembro del grupo que postea
    # botones inline (visibles vía Bot API porque el sender es bot) suele ser
    # spam (porno, promo). Se evalúa con inline_buttons/url/commercial_ad y se
    # banea si dispara. Los bots legítimos sin spam no disparan nada.
    if user.is_bot:
        await _moderate_bot_message(context, db, cfg, msg, user)
        return
    # Mensaje posteado por un usuario VÍA un inline bot (msg.via_bot): el
    # spammer usa @bot inline para postear botones. El sender es el user pero
    # el contenido es del bot. Si tiene botones spam → borrar + avisar admin.
    if getattr(msg, "via_bot", None) is not None:
        if await _moderate_via_bot_message(context, db, cfg, msg, user):
            return

    db.remember_username(user.username, user.id)

    _msg_ts = msg.date.timestamp() if msg.date else None
    if db.is_whitelisted(chat_id, user.id):
        db.record_message(chat_id, user.id, user.username, msg_ts=_msg_ts)
        return

    if user.id == cfg.admin_user_id:
        db.record_message(chat_id, user.id, user.username, msg_ts=_msg_ts)
        return

    # BANEADO QUE SIGUE ESCRIBIENDO. Hasta ahora el bot solo comprobaba la lista de
    # baneados al ENTRAR, así que si un ban federado fallaba en un chat (Telegram
    # devolvió error, el bot no era admin todavía, o alguien lo readmitió a mano),
    # esa persona seguía escribiendo indefinidamente y nadie se enteraba: en la BD
    # constaba como baneada y en el grupo estaba tan tranquila.
    #
    # Caso real: un usuario baneado el 2-ago seguía escribiendo el 3-ago con 156
    # mensajes acumulados. El ban se aplicó en dos de los tres grupos y en el
    # tercero no, y como /ban ni contestaba ni dejaba registro, no hubo forma de
    # notarlo. Ahora cada mensaje suyo re-aplica el ban: la lista federada deja de
    # ser una intención y pasa a cumplirse.
    if db.is_banned(user.id):
        log.warning("baneado ESCRIBIENDO user=%s chat=%s → re-ban", user.id, chat_id)
        decision = Decision(
            action="ban", score=999, rule="federation_known_ban",
            reason=t("reason.federation_rejoin"), payload={"via": "mensaje"},
        )
        await _apply_action(
            context, db, cfg, chat_id=chat_id, chat_title=msg.chat.title,
            user_id=user.id, username=user.username, message_id=msg.message_id,
            decision=decision, original_text=(msg.text or msg.caption),
            first_name=user.first_name,
        )
        return

    # NUEVO: capturar el last_msg_ts PREVIO antes de actualizarlo, para detectar
    # cuentas dormidas que reaparecen mencionando un bot (cuenta hackeada).
    prev_seen = db.get_seen(chat_id, user.id)
    prev_last_ts = (prev_seen["last_msg_ts"] if prev_seen else None)
    dormant_hit = dormant_bot_det.check(msg, last_msg_ts=prev_last_ts)
    if dormant_hit:
        log.info("dormant_bot_mention user=%s chat=%s → ban: %s",
                 user.id, chat_id, dormant_hit.reason[:120])
        decision = Decision(
            action="ban", score=dormant_hit.score, rule=dormant_hit.rule,
            reason=dormant_hit.reason, payload=dormant_hit.payload,
        )
        await _apply_action(
            context, db, cfg, chat_id=chat_id, chat_title=msg.chat.title,
            user_id=user.id, username=user.username, message_id=msg.message_id,
            decision=decision, original_text=(msg.text or msg.caption),
            first_name=user.first_name,
        )
        return

    text_or_caption = msg.text or msg.caption
    # HISTORIA (story): la Bot API la entrega vacía (solo chat+id), así que el
    # mensaje llegaría aquí sin nada que analizar y el spam pasaría limpio. Se pide
    # el texto real por MTProto y se sigue el flujo NORMAL con él: mismos
    # detectores, mismos umbrales. La evidencia es el texto de verdad, así que esto
    # no sube el riesgo de falso positivo. Si no se puede leer, todo queda como antes.
    texto_ajeno = False   # ¿el texto lo redactó un canal ajeno, no este usuario?
    if text_or_caption is None and getattr(msg, "story", None) is not None:
        _leido = await story_reader.leer_caption(context, msg.story)
        if _leido is not None:
            _cap, _ents = _leido
            msg = story_reader.MensajeConTextoDeHistoria(msg, _cap, _ents)
            text_or_caption = _cap
            texto_ajeno = True
    # Una EDICIÓN re-escaneada (via on_edited_message) NO es un mensaje nuevo: no
    # debe contar para msg_count, antiflood ni topweekly (si no, editar varias veces
    # inflaría trust o dispararía un flood falso). Solo corremos los detectores sobre
    # el contenido editado para pillar edit-attacks.
    is_edit = update.edited_message is not None
    if is_edit:
        seen_row = db.get_seen(chat_id, user.id)
        msg_count = int(seen_row["msg_count"]) if seen_row and seen_row["msg_count"] else 1
        db.update_last_message(chat_id, user.id, msg.message_id,
                               None if texto_ajeno else text_or_caption)
    else:
        msg_count = db.record_message(chat_id, user.id, user.username, msg_ts=_msg_ts)
        # Guardar el último mensaje + first_name para revisar tras bans manuales.
        # El caption de una HISTORIA lo redactó un canal ajeno, no este usuario: si se
        # guardara ahí, un "✅ Legítimo" en la revisión lo metería como muestra HAM y
        # envenenaría el clasificador con vocabulario de spam, además de falsear el
        # panel de alfabetos y la vista previa de términos.
        db.update_last_message(chat_id, user.id, msg.message_id,
                               None if texto_ajeno else text_or_caption)
        db.update_seen_first_name(chat_id, user.id, user.first_name)
        # Recolección topweekly:
        # - Media (foto/video/sticker/audio/voice/document/animation) SIEMPRE cuenta.
        # - Solo texto: cuenta si ≥10 chars y no es saludo.
        has_media = bool(
            msg.photo or msg.video or msg.animation or msg.sticker
            or msg.voice or msg.audio or msg.document or msg.video_note
        )
        if has_media:
            db.record_topweekly_msg(chat_id, user.id, len(text_or_caption or ""))
        elif text_or_caption and len(text_or_caption) >= 10 and not greetings.is_greeting(text_or_caption):
            db.record_topweekly_msg(chat_id, user.id, len(text_or_caption))
    is_first = msg_count <= cfg.first_msg_window

    # Antiflood per-user: N mensajes en 60s → mute 6h + revisión del admin. Solo
    # mensajes NUEVOS (una edición no es un mensaje nuevo). Umbral graduado:
    # humano confirmado por admin = 12, veterano = 10, resto = 6.
    if not is_edit and _antiflood_check(context, db, chat_id, user.id):
        log.info("antiflood user=%s chat=%s msg=%s → mute 6h", user.id, chat_id, msg.message_id)
        await _antiflood_apply(context, chat_id, user.id, user, msg.message_id)
        return

    # Reacción amigable a saludos de usuarios marcados como greeters
    greeter_reactions = db.get_friendly_greeter(user.id)
    if greeter_reactions is not None and greetings.is_greeting(msg.text or msg.caption):
        await greetings.react_friendly_delayed(
            context, chat_id, msg.message_id, greeter_reactions, delay=5,
        )

    # @admin mention: si el usuario está reportando algo, gestionarlo y NO seguir
    # el pipeline antispam (no es spam, es un reporte de buena fe).
    # OJO: el caption de una historia lo escribe el spammer en SU canal, así que
    # podría poner "@admins" ahí para saltarse todos los detectores de golpe. La vía
    # de aviso a admins es para humanos pidiendo ayuda, no para texto importado.
    if getattr(msg, "story", None) is None and admin_report.contains_admin_mention(msg):
        await admin_report.handle_admin_mention(context, db, msg)
        return

    text = msg.text or msg.caption or ""
    # Normalización universal: strip zero-width chars + NFKC + casefold para
    # neutralizar homoglyphs (а cirílica vs a latina), ZW evasion, etc.
    normalized_text = learning.normalize(text) if text else ""

    hits: list[Hit] = []
    # 1) Unicode script (sobre texto normalizado)
    hits.append(script_det.check(
        normalized_text or text, is_first_msgs=is_first,
        allowed_scripts=_chat_allowed_scripts(db, chat_id, cfg),
        threshold=cfg.non_latin_ratio_threshold,
    ))
    # 2) External mentions / t.me links (con username del propio chat para
    # distinguir enlaces internos al propio grupo)
    own_username = db.chat_username(chat_id)
    hits.append(ext_det.check(
        msg, chat_id=chat_id, is_first_msg=is_first,
        detect_user_mentions=cfg.detect_external_mentions,
        detect_tg_links=cfg.detect_external_tg_links,
        is_user_in_chat=db.known_user_in_chat,
        resolve_username=db.resolve_username,
        own_chat_username=own_username,
    ))
    # 3) URL blocklist
    hits.append(url_det.check(msg, cfg.url_blocklist, is_first_msg=is_first))
    # 3b) tg:// deeplinks phishing
    hits.append(tgdeep_det.check(msg, is_first_msg=is_first))
    # 3c) Premium + nueva cuenta + link en primer msg (señales via Telethon)
    if is_first and user.is_premium:
        reporter = context.bot_data.get("reporter")
        client = reporter.get_client() if reporter else None
        if client is not None:
            try:
                sig = await user_signals.fetch(client, user.id, chat_id=chat_id, first_name=user.first_name)
                hits.append(premium_det.check(
                    msg, is_first_msg=is_first, user_is_premium=True,
                    user_signals_age_days=(sig.account_age_days if sig else None),
                    user_signals_photo_count=(sig.photo_count if sig else 0),
                ))
            except Exception as exc:
                log.debug("premium_new_link signals fallo: %s", exc)
    # 3d) Join-to-First-Message delta
    if is_first:
        seen_row = db.get_seen(chat_id, user.id)
        if seen_row and seen_row["join_ts"] and seen_row["first_msg_ts"]:
            delta = float(seen_row["first_msg_ts"]) - float(seen_row["join_ts"])
            hits.append(jfm_det.check(is_first_msg=True, delta_seconds=delta))
    # 3d-pre) Mensaje con botones inline → users normales no pueden enviarlos.
    # Casi siempre es forward desde canal/bot promocional.
    hits.append(buttons_det.check(msg))
    # 3d-ter) Contacto compartido cuyo nombre/vCard es el reclamo de spam (el texto
    # va en msg.contact, no en msg.text, así que el resto de detectores no lo ven).
    hits.append(contact_det.check(
        msg, _chat_allowed_scripts(db, chat_id, cfg), cfg.non_latin_ratio_threshold, is_first_msg=is_first,
    ))
    # 3d-ter2) Promoción de canal externo mediante cita a otro chat (external_reply):
    # el reclamo va en la cita y el texto visible es un CTA mínimo ("Please Join").
    hits.append(extreply_det.check(msg, is_first_msg=is_first, is_moderated_chat=cfg.is_moderated))
    # 3d-quat) Detectores de dinero/trabajo (anuncio comercial + testimonio de
    # estafa de inversión). Su agresividad la modula el ajuste money_guard del chat:
    # 'normal' (defecto), 'soft' (solo casos muy claros) u 'off'. Es lo que pediste
    # para poder relajar los bans por mensajes de trabajo/dinero en el primer mensaje.
    # Antes de mirar el contenido, se le quita el disfraz: una sola letra cambiada
    # por su gemela cirílica dejaba `commercial_ad` en 0 sin que saltara nada más
    # (medido: 75 → 0 cambiando la «o» de «euros»), y el espaciado letra a letra
    # tampoco casaba con ningún patrón. Solo lo ven los detectores de texto plano:
    # los de enlaces y menciones siguen con el mensaje original, cuyas entidades no
    # se pueden descuadrar. Ver `desofuscar.py`.
    msg_txt, _trucos = desofuscar.para_detectores(msg)
    if _trucos:
        log.info("texto disfrazado (%s) user=%s chat=%s → se evalúa el texto limpio",
                 "+".join(_trucos), user.id, chat_id)
    _money_guard = (_chat_money_guard(db, chat_id))
    hits.append(_apply_money_guard(comad_det.check(msg_txt, is_first_msg=is_first), _money_guard))
    # Testimonio "di X, me devolvieron Y mayor" con elogio y llamada a contactar.
    # Sin este detector se colaba cuando no ponían @usuario final (lo único que lo
    # cazaba era external_mention).
    hits.append(_apply_money_guard(invscam_det.check(msg_txt, is_first_msg=is_first), _money_guard))
    # 3d-quint) Primer mensaje dominado por emojis sin texto real (captación
    # de atención típica de spam, ej. "🍭🍄🌟").
    hits.append(emoji_only_det.check(msg, is_first_msg=is_first))
    # 3d-cinq) El MISMO texto, a la vez, en varios de nuestros grupos. Aprovecha la
    # federación: quien modera un solo grupo no puede ver esto. No mira el
    # contenido, así que caza campañas cuyo vocabulario las listas todavía no
    # conocen. El texto ya viene normalizado, así que cambiar mayúsculas o meter
    # caracteres invisibles no sirve para esquivarlo.
    if not texto_ajeno:
        hits.append(crosspost_det.check(db, chat_id, user.id, normalized_text or text))

    # 3d-sext) "Este es mi número de <otra app>, escríbeme ahí". Sin enlace, sin
    # mención y en español correcto, así que ningún otro detector lo veía: hubo que
    # borrarlo a mano tras hora y cuarto en el grupo.
    hits.append(offplat_det.check(msg_txt, is_first_msg=is_first))
    # 3d-bis) Forward desde canal/bot en primer mensaje o primeros 3 min → ban directo
    seen_row_fwd = db.get_seen(chat_id, user.id)
    secs_since_first = None
    if seen_row_fwd and seen_row_fwd["first_seen_ts"] is not None:
        # Hora de EVENTO en ambos lados (msg.date y first_seen_ts) para que el
        # delta sea consistente, igual que jfm_delta. Usar time.time() (proceso)
        # aquí solo desviaría el delta tras un backlog (hacia falso negativo).
        now_evt = msg.date.timestamp() if msg.date else time.time()
        secs_since_first = max(0.0, now_evt - float(seen_row_fwd["first_seen_ts"]))
    hits.append(fwd_det.check(
        msg, is_first_msg=is_first, seconds_since_first_seen=secs_since_first,
    ))
    # 3d bis) HISTORIA compartida recién entrado. Va aquí, y NO dentro del bloque de
    # `is_first`, porque también cubre al que ya habló una vez. Solo Bot API: es la
    # única defensa de quien instale el bot sin Telethon, que no puede leer el
    # contenido. Si Telethon sí está y pudo leerlo, los detectores de contenido ya
    # habrán aportado su score y ambos se suman.
    if getattr(msg, "story", None) is not None:
        _seen_st = db.get_seen(chat_id, user.id)
        _join_ts = _seen_st["join_ts"] if _seen_st is not None else None
        hits.append(story_det.check(
            msg,
            user_id=user.id,
            is_first_msg=is_first,
            bot_saw_join=_join_ts is not None,
            seconds_since_join=(time.time() - _join_ts) if _join_ts else None,
            # Cuántos mensajes ha escrito AQUÍ: distingue al que participa de
            # verdad del que lleva meses callado y de repente planta una historia.
            msg_count=(_seen_st["msg_count"] if _seen_st is not None else None),
        ))

    # 3d ter) LISTAS EXTERNAS en los primeros mensajes, no solo al entrar.
    #
    # Caso real: un spammer entró el 1-ago, lols.bot todavía no lo tenía fichado, y
    # se coló. Escribió el día 3, y para entonces lols YA lo tenía (lo marcó a las
    # 08:16 UTC; nosotros baneamos a las 08:27, once minutos tarde y por el idioma
    # del mensaje, no por la lista). Consultando también aquí, ese caso cae por
    # lols con cualquier texto, incluso si escribe en español perfecto.
    #
    # Solo en los primeros mensajes: quien ya participa no se re-consulta, así el
    # coste en llamadas queda acotado a los recién llegados. CAS ya cachea; para
    # lols se cachea en memoria, que basta para no repetir dentro de la ráfaga.
    if is_first and not db.is_whitelisted(chat_id, user.id):
        _sess = context.bot_data.get("http")
        if _sess is not None:
            _cache = context.bot_data.setdefault("_lols_cache", {})
            _ahora = time.time()
            if cfg.lols_enabled:
                _cached = _cache.get(user.id)
                if _cached is None or _ahora - _cached[0] > 3600:
                    try:
                        _h = await lols_det.check(user.id, _sess)
                        _cache[user.id] = (_ahora, bool(_h), _h)
                    except Exception as exc:  # noqa: BLE001
                        log.debug("lols en primer mensaje falló user=%s: %s", user.id, exc)
                        _cache[user.id] = (_ahora, False, None)
                    _cached = _cache.get(user.id)
                if _cached and _cached[1] and _cached[2]:
                    log.info("lols_match en primer mensaje user=%s chat=%s", user.id, chat_id)
                    hits.append(_cached[2])
            if cfg.cas_enabled:
                try:
                    _c = await cas_det.check(user.id, _sess, db, cfg.cas_cache_ttl_seconds)
                    if _c:
                        log.info("cas_match en primer mensaje user=%s chat=%s", user.id, chat_id)
                        hits.append(_c)
                except Exception as exc:  # noqa: BLE001
                    log.debug("CAS en primer mensaje falló user=%s: %s", user.id, exc)

    # 3e) Primer mensaje es media + cuenta sospechosa (patrón spam 2025).
    # GUARD anti-falso-positivo: solo aplicar si el bot presenció el JOIN del user.
    # Si join_ts IS NULL, el user ya estaba en el grupo antes que el bot → NO sabemos
    # si es realmente "primer mensaje", podría llevar años. Saltar la regla.
    if is_first:
        seen_row_fm = db.get_seen(chat_id, user.id)
        bot_saw_join = seen_row_fm is not None and seen_row_fm["join_ts"] is not None
        # MISMA lista que topweekly y que /scan. Estaban desalineadas: sin voice ni
        # audio, `/scan` decía «tiene media» ante una nota de voz y el detector no
        # podía saltar nunca, o sea el comando que explica qué pasaría mentía.
        has_media = bool(
            msg.photo or msg.video or msg.animation or msg.sticker
            or msg.voice or msg.audio or msg.document or msg.video_note
        )
        if has_media and bot_saw_join:
            # Calcular sospecha: reusamos verification._is_suspicious_profile
            sig_local = None
            reporter = context.bot_data.get("reporter")
            client = reporter.get_client() if reporter else None
            if client is not None:
                try:
                    sig_local = await user_signals.fetch(client, user.id, chat_id=chat_id, first_name=user.first_name)
                except Exception:
                    pass
            # Si Telethon no pudo dar señales, NO marcar suspicious por defecto
            # (provocaba falsos positivos cuando el reporter estaba desconectado)
            if sig_local is None:
                suspicious, susp_reasons = False, []
            else:
                suspicious, susp_reasons = verification._is_suspicious_profile(
                    sig_local, user.username, user.first_name, user.last_name,
                )
            hits.append(media_det.check(
                msg, is_first_msg=True, is_suspicious=suspicious,
                # el detector solo los muestra: se le pasan ya traducidos
                suspicious_reasons=verification.render_reason_list(susp_reasons),
            ))
        elif has_media and not bot_saw_join:
            log.info(
                "first_msg_media SKIP user=%s chat=%s: join no presenciado (user pre-existente)",
                user.id, chat_id,
            )
    # 4) Similarity contra samples aprendidos (cosine char-ngrams)
    spam_samples = db.recent_sample_texts(label="spam", limit=200, since_days=90)
    ham_samples = db.recent_sample_texts(label="ham", limit=200, since_days=90)
    if spam_samples or ham_samples:
        learned_score, sample_match = learning.check_against_samples(text, spam_samples, ham_samples)
        if learned_score != 0:
            hits.append(Hit(
                rule="learned_similarity" if learned_score > 0 else "learned_negative",
                score=learned_score,
                reason=(t("reason.learned_spam_match", sample=(sample_match or "")[:60])
                        if learned_score > 0 else t("reason.learned_ham_match")),
                payload={"sample_match": sample_match} if sample_match else None,
            ))

    real = [h for h in hits if h]
    if not real:
        return

    # Filtrar reglas suprimidas (admin marcó "no era spam").
    real = [h for h in real if not db.is_suppressed(user.id, h.rule)]
    if not real:
        log.info("Hits suprimidos para user %s", user.id)
        return

    # 5) ¿A DÓNDE lleva el enlace? Un t.me a un chat externo es una señal ciega: no
    # sabe distinguir un canal de domótica de uno de packs, y con esa duda solo se
    # puede ser blando. El destino, en cambio, se presenta solo. Se mira únicamente
    # cuando ya hay un hit de enlace, así que son unas pocas consultas al día.
    enlaces_tg = _enlaces_tg_de(real)
    if enlaces_tg:
        destino = await link_reader.leer(context, enlaces_tg, es_moderado=cfg.is_moderated)
        destino_hit = link_target_det.check(destino)
        if destino_hit:
            log.info(
                "link_target_spam user=%s chat=%s destino=%r → el enlace deja de ser borderline",
                user.id, chat_id, (destino.titulo or "")[:60],
            )
            real.append(destino_hit)

    # Trust graduation: si solo dispararon reglas "borderline" (mención/link)
    # Y el user tiene >10 msgs + >10 días en el grupo → aviso suave en vez de ban
    BORDERLINE = {"external_mention_or_link", "url_blocklist", "tg_deeplink"}
    only_borderline = all(h.rule in BORDERLINE for h in real)
    if only_borderline and gentle_warning.is_trusted(db, chat_id, user.id):
        reason = " | ".join(h.reason for h in real)
        log.info("user=%s trusted en chat=%s → gentle_warning en lugar de acción", user.id, chat_id)
        await gentle_warning.send(context, db, msg, reason_hint=reason[:200])
        # Logamos en moderation_log para auditoría
        db.log_action(
            chat_id=chat_id, user_id=user.id, username=user.username,
            message_id=msg.message_id,
            rule="+".join(h.rule for h in real), action="gentle_warn",
            score=sum(h.score for h in real),
            mode=("shadow" if cfg.shadow else "active"),
            payload={"reason": reason, "trust": "granted"},
        )
        # Y se le cuenta al admin. El aviso suave se autoborra a los 5 min y el
        # mensaje del veterano se queda: si nadie mira, el bot ha visto spam, ha
        # decidido no tocarlo y no se ha enterado nadie. Pasó de verdad (24/07/2026:
        # un enlace a un canal de packs sobrevivió porque su autor llevaba dos años
        # en el grupo, y quien avisó fue otro miembro). Mismo aviso y mismos botones
        # que el atajo por trust alto: nada / avisar / banear.
        await _send_trust_notice(
            context, db, cfg, msg, user,
            rules=[h.rule for h in real], reason=reason,
            proposed_action="gentle_warn",
            trust=_trust_score_cached(context, db, chat_id, user.id),
        )
        return

    is_first_attack = is_first and any(
        h.rule in ("non_allowed_script", "external_mention_or_link") for h in real
    )
    # Umbrales: los de siempre, salvo que esta persona haya llegado con una
    # avalancha de entradas, y entonces un peldaño más abajo. No es una acción
    # nueva ni una regla nueva: es la misma escala, con la duda resolviéndose al
    # revés durante unos minutos. A quien ya estaba en el grupo no le afecta.
    _ban_s, _kick_s, _mute_s = antiraid.umbrales(
        context, cfg, chat_id, (prev_seen["join_ts"] if prev_seen is not None else None))
    decision = decide(
        real, _ban_s, _kick_s, _mute_s,
        cfg.first_msg_attack_action, is_first_msg_attack=is_first_attack,
    )

    # Modo suave del chat: silenciar para siempre en vez de expulsar. Un falso
    # positivo con mute se deshace sin que la persona se entere; uno con ban la
    # obliga a pedir entrar otra vez, y mucha gente no vuelve.
    #
    # NO se aplica a las reglas duras (CAS, lols, ban federado, reaction farming):
    # ahí no hay duda que proteger, son spammers confirmados, y dejarlos dentro
    # mudos es dejarlos dentro. El modo suave existe para la zona gris, no para
    # ablandar lo que ya está probado.
    if decision.action == "ban" and _modo_suave(db, chat_id, cfg) and not any(
            h.rule in HARD_RULES_BAN for h in real):
        log.info("modo suave en chat=%s: user=%s se silencia en vez de expulsarse (reglas=%s)",
                 chat_id, user.id, [h.rule for h in real])
        decision = Decision(
            action="mute", score=decision.score, rule=decision.rule,
            reason=decision.reason + " | " + t("reason.soft_ban"),
            payload={**(decision.payload or {}), "soft_ban": True},
        )

    # Trust score genérico (0-100): degradar acción para users de confianza.
    # Excepciones: reglas de severidad máxima nunca se degradan.
    HARD_RULES = HARD_RULES_BAN
    has_hard_rule = any(h.rule in HARD_RULES for h in real)
    if not has_hard_rule and decision.action != "noop":
        trust = _trust_score_cached(context, db, chat_id, user.id)
        # Trust medio (40-69) Y acción severa (ban/kick) → REVIEW por admin
        # en lugar de actuar directamente. El bot pregunta y aprende de la respuesta.
        if 40 <= trust < 70 and decision.action in ("ban", "kick"):
            log.info(
                "user=%s trust=%d → REVIEW admin (acción sería %s, reglas=%s)",
                user.id, trust, decision.action, [h.rule for h in real],
            )
            await _send_review_request(
                context, db, msg, user,
                rules=[h.rule for h in real],
                reason=" | ".join(h.reason for h in real)[:300],
                proposed_action=decision.action,
                trust=trust,
            )
            db.log_action(
                chat_id=chat_id, user_id=user.id, username=user.username,
                message_id=msg.message_id,
                rule="+".join(h.rule for h in real), action="pending_review",
                score=decision.score, mode=("shadow" if cfg.shadow else "active"),
                payload={"trust": trust, "would_be": decision.action},
            )
            return
        if trust >= 70:
            log.info(
                "user=%s trust=%d en chat=%s → SKIP (acción %s anulada por trust alto, reglas=%s)",
                user.id, trust, chat_id, decision.action, [h.rule for h in real],
            )
            # El bot no actúa, pero calla del todo tampoco: alguien de confianza
            # puede tener la cuenta robada, o estar compartiendo algo sin mirar.
            # Aviso SOLO por privado (nunca en el grupo: señalar en público a un
            # veterano por algo que el bot ha decidido no castigar sería peor que
            # el spam) y con la decisión en tus manos.
            if decision.action in ("ban", "kick"):
                await _send_trust_notice(
                    context, db, cfg, msg, user,
                    rules=[h.rule for h in real],
                    reason=" | ".join(h.reason for h in real)[:300],
                    proposed_action=decision.action,
                    trust=trust,
                )
            db.log_action(
                chat_id=chat_id, user_id=user.id, username=user.username,
                message_id=msg.message_id,
                rule="+".join(h.rule for h in real), action="noop_trust",
                score=decision.score, mode=("shadow" if cfg.shadow else "active"),
                payload={"trust": trust, "would_be": decision.action},
            )
            return
        if trust >= 40:
            downgrade = {"ban": "mute", "kick": "mute", "mute": "noop", "delete": "noop"}
            new_action = downgrade.get(decision.action, decision.action)
            if new_action != decision.action:
                log.info(
                    "user=%s trust=%d → degradado %s → %s (reglas=%s)",
                    user.id, trust, decision.action, new_action, [h.rule for h in real],
                )
                decision = Decision(
                    action=new_action, score=decision.score, rule=decision.rule,
                    reason=decision.reason,
                    payload={**(decision.payload or {}), "trust_degraded_from": decision.action, "trust": trust},
                )
                if new_action == "noop":
                    db.log_action(
                        chat_id=chat_id, user_id=user.id, username=user.username,
                        message_id=msg.message_id,
                        rule="+".join(h.rule for h in real), action="noop_trust",
                        score=decision.score, mode=("shadow" if cfg.shadow else "active"),
                        payload={"trust": trust, "would_be": "mute/delete"},
                    )
                    return

    await _apply_action(
        context, db, cfg,
        chat_id=chat_id, chat_title=msg.chat.title,
        user_id=user.id, username=user.username,
        message_id=msg.message_id, decision=decision,
        original_text=text, first_name=user.first_name,
    )


async def on_message_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.bot_data["cfg"]
    if not cfg.reaction_farming_enabled:
        return
    db: DB = context.bot_data["db"]
    mru = update.message_reaction
    if not mru or not mru.user:
        return
    user = mru.user
    if user.is_bot or user.id == cfg.admin_user_id:
        return
    await _ensure_chat_registered(context, db, mru.chat)
    if not cfg.is_moderated(mru.chat.id):
        return
    # Guard whitelist: users marcados como inmunes no disparan reaction-farming
    if db.is_whitelisted(mru.chat.id, user.id):
        return
    # Incluye tanto emojis estándar como custom_emoji_id (Telegram premium)
    new_emojis: list[str] = []
    for r in (mru.new_reaction or []):
        if hasattr(r, "emoji") and r.emoji:
            new_emojis.append(r.emoji)
        elif hasattr(r, "custom_emoji_id") and r.custom_emoji_id:
            new_emojis.append(f"custom:{r.custom_emoji_id}")
    db.record_reaction(mru.chat.id, user.id, mru.message_id, new_emojis)

    # Si user nunca ha escrito mensajes y ha reaccionado mucho en ventana → ban
    total_msgs = db.total_msgs_user(user.id)
    if total_msgs > 0:
        return
    since = react_det.window_start_ts(cfg.reaction_threshold_seconds)
    count = db.reactions_in_window(user.id, since)
    hit = react_det.check(
        user_id=user.id, total_msgs_user=total_msgs,
        reactions_in_window=count,
        threshold_count=cfg.reaction_threshold_count,
        threshold_seconds=cfg.reaction_threshold_seconds,
    )
    if not hit:
        return
    if db.is_suppressed(user.id, hit.rule):
        return
    decision = decide(
        [hit], cfg.ban_score, cfg.kick_score, cfg.mute_score,
        cfg.first_msg_attack_action, is_first_msg_attack=False,
    )
    await _apply_action(
        context, db, cfg,
        chat_id=mru.chat.id, chat_title=mru.chat.title,
        user_id=user.id, username=user.username,
        message_id=mru.message_id, decision=decision,
        original_text=t("hdl.reaction_farming_text", count=count,
                        seconds=cfg.reaction_threshold_seconds),
        first_name=user.first_name,
    )


# ---------------- Aplicar acción ----------------


_ADMIN_CACHE_MAX = 5000
_TRUST_CACHE_MAX = 10000
_TRUST_CACHE_TTL = 60  # segundos


def _trust_score_cached(context: ContextTypes.DEFAULT_TYPE, db: DB,
                        chat_id: int, user_id: int) -> int:
    """Trust score con cache TTL 60s. Evita N queries SQL por cada mensaje."""
    cache = context.bot_data.setdefault("_trust_cache", {})
    key = (chat_id, user_id)
    now = time.time()
    entry = cache.get(key)
    if entry and entry[1] > now:
        return entry[0]
    score = db.user_trust_score(chat_id, user_id)
    # Bound del cache
    if len(cache) >= _TRUST_CACHE_MAX:
        expired = [k for k, (_, exp) in cache.items() if exp <= now]
        for k in expired:
            cache.pop(k, None)
        if len(cache) >= _TRUST_CACHE_MAX:
            oldest_half = sorted(cache.items(), key=lambda kv: kv[1][1])[: len(cache) // 2]
            for k, _ in oldest_half:
                cache.pop(k, None)
    cache[key] = (score, now + _TRUST_CACHE_TTL)
    return score


def invalidate_trust_cache(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    """Invalida el cache de trust para un user (llamar tras añadir/quitar warns)."""
    cache = context.bot_data.get("_trust_cache")
    if cache:
        cache.pop((chat_id, user_id), None)


async def _is_admin_of_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    """Comprueba si el user es admin/owner del chat. Resultado se cachea por (chat,user) durante 5 min.

    Purga entries expiradas si el cache supera _ADMIN_CACHE_MAX, evitando crecimiento
    indefinido en grupos muy activos con miles de users distintos.
    """
    cache = context.bot_data.setdefault("_admin_cache", {})
    key = (chat_id, user_id)
    now = time.time()
    if key in cache and cache[key][1] > now:
        return cache[key][0]
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        is_admin = member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception as exc:  # noqa: BLE001
        # FALLA DEL LADO SEGURO: si no se puede comprobar, se asume que SÍ es admin
        # y no se actúa. Antes devolvía False y un fallo transitorio de red bastaba
        # para que la guarda dejara de proteger y se baneara a un admin. La regla
        # del proyecto es que un falso positivo es peor que un falso negativo: el
        # spammer se cazará en su siguiente mensaje, pero un admin baneado no se
        # arregla solo. NO se cachea el resultado, para reintentar la próxima vez.
        log.warning("is_admin_of_chat: no se pudo comprobar chat=%s user=%s (%s); "
                    "se asume admin y NO se actúa", chat_id, user_id, exc)
        return True
    # Bound: si el cache supera el máximo, purga expiradas y, si sigue lleno, descarta la mitad más vieja
    if len(cache) >= _ADMIN_CACHE_MAX:
        expired = [k for k, (_, exp) in cache.items() if exp <= now]
        for k in expired:
            cache.pop(k, None)
        if len(cache) >= _ADMIN_CACHE_MAX:
            oldest_half = sorted(cache.items(), key=lambda kv: kv[1][1])[: len(cache) // 2]
            for k, _ in oldest_half:
                cache.pop(k, None)
    cache[key] = (is_admin, now + 300)
    return is_admin


# Reglas de ALTA confianza que pueden generar reporte a Telegram via Telethon.
# Las demás reglas pueden tener FP (url_blocklist, mention solo, script solo) y
# reportarlas baja el "trust" de la cuenta Telethon como reporter.
_REPORTABLE_RULES = frozenset({
    "cas_match",                  # 100% match con lista CAS
    "lols_match",                 # 100% match con lols.bot
    "federation_known_ban",       # ya baneado en federación previa
    "reaction_farming",           # patrón claro de bot lurker
    "forward_first_msg",          # forward desde canal/bot en primer msg
    "first_msg_media",            # foto/video en primer msg (típico spam)
    "learned_similarity",         # similitud con sample previo confirmado
    "obvious_spam_profile",       # perfil con múltiples señales de spammer al entrar
    "bio_spam",                   # bio con invite link + emojis sexuales / commerce
    "inline_buttons_from_user",   # users normales no pueden enviar reply_markup
    "photos_batch_upload",        # fotos de perfil subidas en ráfaga = identidad robada
    "commercial_ad",              # anuncio comercial estructurado (multi-señal)
})

# Score mínimo combinado para que un ban genere reporte oficial. Evita
# reportar bans que apenas superan el umbral por una sola regla borderline.
_REPORT_MIN_SCORE = 150


def _is_reportable(decision) -> bool:
    """Decide si un ban debe enviarse a Telegram via channels.reportSpam.

    Requisitos:
      - Al menos una regla disparada está en `_REPORTABLE_RULES`.
      - decision.score >= _REPORT_MIN_SCORE (excepto las reglas single-shot de
        confianza máxima: cas_match, lols_match, federation_known_ban, que
        bypasean el threshold porque ya son 100% certeza por sí solas).

    Nota: `decision.rule` puede ser "regla1+regla2" cuando varias dispararon.
    """
    rules = set((decision.rule or "").split("+"))
    if not (rules & _REPORTABLE_RULES):
        return False
    single_shot = {"cas_match", "lols_match", "federation_known_ban"}
    if rules & single_shot:
        return True
    return decision.score >= _REPORT_MIN_SCORE


async def _quitar_botones(q) -> None:
    """Quita los botones de un aviso ya resuelto, tragándose el error del doble toque.

    Sin esto, pulsar dos veces rápido devuelve «message is not modified», que sube
    hasta el manejador de errores y le manda al admin un traceback de «error interno
    del bot» por haber hecho doble clic.
    """
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass


async def _send_trust_notice(
    context: ContextTypes.DEFAULT_TYPE,
    db: DB,
    cfg: Config,
    msg,
    user,
    rules: list[str],
    reason: str,
    proposed_action: str,
    trust: int,
) -> None:
    """Aviso al admin cuando el trust alto ha ANULADO una acción severa.

    Antes esto era un silencio total: el bot decidía no tocar a un veterano y no lo
    contaba. Pero una cuenta de confianza puede estar robada, o su dueño puede haber
    compartido algo sin mirar. El admin decide: nada / avisar / banear.

    Solo por privado. Un aviso público sobre un veterano al que el bot ha decidido
    NO castigar haría más daño que el propio mensaje.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    if not notify_prefs.effective(db, "trust_skip", cfg):
        return
    admin_dm = cfg.admin_notify_chat_id
    if not admin_dm:
        return
    texto = msg.text or msg.caption or t("hdl.no_text")
    info = t(
        "hdl.trust_notice_dm",
        uid=user.id,
        # Todo lo que viene de fuera se escapa: el TÍTULO del canal de origen entra
        # en `reason` y lo elige quien monta el canal de spam. Un canal llamado
        # «<b>Signals» dejaba el HTML sin cerrar, Telegram rechazaba el mensaje
        # entero y el aviso se perdía en silencio: el spammer decidía si te enterabas.
        name=_h.escape((user.first_name or "user")[:40]),
        trust=_trust.render_trust(trust),
        chat=_h.escape(str(msg.chat.title or msg.chat_id)),
        rules=_h.escape(", ".join(rules)),
        action=_h.escape(proposed_action),
        reason=_h.escape(reason),
        text=_h.escape(texto[:600]),
    )
    # callback_data: tnote:<nada|warn|ban>:CHAT:USER:MSG (dentro de los 64 bytes)
    base = f"{msg.chat_id}:{user.id}:{msg.message_id}"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(t("hdl.btn.tn_nothing"), callback_data=f"tnote:nada:{base}"),
        InlineKeyboardButton(t("hdl.btn.tn_warn"), callback_data=f"tnote:warn:{base}"),
        InlineKeyboardButton(t("hdl.btn.tn_ban"), callback_data=f"tnote:ban:{base}"),
    ], [notify_prefs.mute_button("trust_skip")]])
    try:
        await context.bot.send_message(
            chat_id=admin_dm, text=info, parse_mode="HTML", reply_markup=kb,
            disable_web_page_preview=True,
        )
    except TelegramError as exc:
        log.warning("trust notice DM fallo: %s", exc)


async def on_trust_notice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Botones nada / avisar / banear del aviso de trust alto."""
    q = update.callback_query
    if q is None:
        return
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer(t("hdl.only_admin_review"))
        return
    try:
        _, verdicto, chat_s, user_s, msg_s = q.data.split(":", 4)
        chat_id, user_id, msg_id = int(chat_s), int(user_s), int(msg_s)
    except Exception as exc:  # noqa: BLE001
        await q.answer(t("hdl.callback_invalid", error=exc))
        return

    if verdicto == "nada":
        db.log_action(
            chat_id=chat_id, user_id=user_id, username=None, message_id=msg_id,
            rule="admin_trust_notice", action="noop", score=0,
            mode=("shadow" if cfg.shadow else "active"), payload={"via": "trust_notice"},
        )
        await q.answer(t("hdl.tn_ack_nothing"))
        await _quitar_botones(q)
        return

    if verdicto == "warn":
        # Misma vía que /warn: publica en el grupo, borra el mensaje y ejecuta la
        # acción configurada si se llega al límite. Antes solo apuntaba el warn en
        # la BD: el usuario no se enteraba y su tercer aviso de tres no sancionaba.
        from . import warns_mod
        objetivo = None
        try:
            miembro = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            objetivo = miembro.user
        except TelegramError as exc:
            log.debug("trust notice warn: no se pudo leer el miembro %s: %s", user_id, exc)
        n = await warns_mod.aplicar_warn(
            context, chat_id=chat_id, target_id=user_id, target_user=objetivo,
            by_admin=cfg.admin_user_id, reason=t("hdl.tn_warn_reason"),
            target_msg_id=msg_id,
        )
        db.log_action(
            chat_id=chat_id, user_id=user_id, username=None, message_id=msg_id,
            rule="admin_trust_notice", action="warn", score=0,
            mode=("shadow" if cfg.shadow else "active"), payload={"via": "trust_notice", "n": n},
        )
        await q.answer(t("hdl.tn_ack_warn", n=n))
        await _quitar_botones(q)
        return

    # banear: se borra el mensaje y se federa, igual que cualquier otro ban.
    # El borrado va DETRÁS de la guarda de shadow: en modo prueba el bot no toca
    # nada del grupo, y aquí se estaba saltando esa regla.
    if not cfg.shadow:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except TelegramError:
            pass
    await federate_ban(
        context.bot, db, user_id=user_id, reason=t("hdl.tn_ban_reason"),
        rule="admin_trust_notice", triggered_in_chat=chat_id, shadow=cfg.shadow,
    )
    # Auditoría obligatoria: sin esto el ban no salía en /recent ni en /stats, y el
    # único rastro era el `noop_trust` de cuando se envió el aviso, que dice
    # exactamente lo contrario de lo que acabó pasando.
    db.log_action(
        chat_id=chat_id, user_id=user_id, username=None, message_id=msg_id,
        rule="admin_trust_notice", action="ban", score=0,
        mode=("shadow" if cfg.shadow else "active"), payload={"via": "trust_notice"},
    )
    await q.answer(t("hdl.tn_ack_ban"))
    await _quitar_botones(q)


async def _send_review_request(
    context: ContextTypes.DEFAULT_TYPE,
    db: DB,
    msg,
    user,
    rules: list[str],
    reason: str,
    proposed_action: str,
    trust: int,
) -> None:
    """Publica aviso público breve y DM al admin con botones legítimo/spam.

    Si el admin pulsa "Legítimo": añade msg a samples ham, borra aviso, suprime regla.
    Si pulsa "Spam": añade a samples spam, ejecuta ban + delete + cleanup.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    cfg: Config = context.bot_data["cfg"]
    chat_id = msg.chat_id
    msg_id = msg.message_id
    user_id = user.id

    # 1) Aviso público breve (autoborrado 6h)
    aviso_txt = t("hdl.review_public_notice")
    try:
        public = await context.bot.send_message(
            chat_id=chat_id, text=aviso_txt, parse_mode="HTML",
            reply_to_message_id=msg_id, disable_notification=True,
        )
        jq = context.application.job_queue
        if jq is not None and public is not None:
            jq.run_once(
                borrado_diferido.borrar_mensaje_job, when=6 * 3600,
                data={"chat_id": chat_id, "message_id": public.message_id},
                name=f"del_review_aviso_{chat_id}_{public.message_id}",
            )
    except TelegramError as exc:
        log.warning("review aviso send fallo: %s", exc)
        public = None

    # 2) DM al admin con copia del msg + botones
    admin_dm = cfg.admin_notify_chat_id
    if not admin_dm:
        return
    public_msg_id = public.message_id if public else 0
    text = msg.text or msg.caption or "(sin texto)"
    name = (user.first_name or "user")[:40]
    info = t(
        "hdl.review_dm",
        uid=user_id,
        # Mismo motivo que en _send_trust_notice: `reason` y el nombre los controla
        # quien manda el mensaje. Sin escapar, un `<b>` suelto tumba el aviso entero.
        name=_h.escape(name),
        trust=_trust.render_trust(trust),
        chat=_h.escape(str(msg.chat.title or chat_id)),
        rules=_h.escape(", ".join(rules)),
        action=_h.escape(proposed_action),
        reason=_h.escape(reason),
        text=_h.escape(text[:600]),
    )
    # callback_data: prev:legit:CHAT:USER:MSG:PUBLIC  /  prev:spam:CHAT:USER:MSG:PUBLIC
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(t("hdl.btn.legit"), callback_data=f"prev:legit:{chat_id}:{user_id}:{msg_id}:{public_msg_id}"),
        InlineKeyboardButton(t("hdl.btn.spam"), callback_data=f"prev:spam:{chat_id}:{user_id}:{msg_id}:{public_msg_id}"),
    ]])
    try:
        await context.bot.send_message(
            chat_id=admin_dm, text=info, parse_mode="HTML",
            reply_markup=kb, disable_notification=False,
            disable_web_page_preview=True,
        )
    except TelegramError as exc:
        log.warning("review DM admin fallo: %s", exc)


async def on_pending_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja botones Legítimo/Spam del DM admin sobre msgs en review."""
    q = update.callback_query
    if q is None:
        return
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer(t("hdl.only_admin_review"))
        return
    try:
        _, verdict, chat_s, user_s, msg_s, public_s = q.data.split(":", 5)
        chat_id = int(chat_s)
        user_id = int(user_s)
        msg_id = int(msg_s)
        public_id = int(public_s)
    except Exception as exc:  # noqa: BLE001
        await q.answer(t("hdl.callback_invalid", error=exc))
        return

    # Recuperar texto del msg vía seen_users.last_msg_text (lo guardamos al recibirlo)
    seen = db.get_seen(chat_id, user_id)
    text = (seen["last_msg_text"] if seen else "") or ""

    if verdict == "legit":
        # Añadir a samples ham + borrar aviso público + suprimir reglas para ese user
        if text and len(text) >= 5:
            norm = learning.normalize(text)
            db.add_sample(
                text_norm=norm, text_hash=learning.text_hash(norm), label="ham",
                added_by=cfg.admin_user_id, chat_id=chat_id, source_user=user_id,
            )
        # Borrar el aviso público
        if public_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=public_id)
            except TelegramError:
                pass
        # Editar el DM para marcar resuelto
        try:
            await q.edit_message_text(
                f"{q.message.text_html or q.message.text}{t('hdl.review_legit_suffix')}",
                parse_mode="HTML", disable_web_page_preview=True,
            )
        except TelegramError:
            pass
        await q.answer(t("hdl.review_legit_toast"))
        db.log_action(
            chat_id=chat_id, user_id=user_id, username=None,
            message_id=msg_id, rule="review_resolved", action="noop_legit",
            score=0, mode=("shadow" if cfg.shadow else "active"),
            payload={"verdict": "legit"},
        )
        return

    # verdict == "spam": ejecutar ban federado + delete + samples spam
    if text and len(text) >= 5:
        norm = learning.normalize(text)
        db.add_sample(
            text_norm=norm, text_hash=learning.text_hash(norm), label="spam",
            added_by=cfg.admin_user_id, chat_id=chat_id, source_user=user_id,
        )
    # Borrar msg original + ban federado
    decision = Decision(
        action="ban", score=200, rule="manual_admin_ban",
        reason=t("reason.review_confirmed_spam"),
        payload={"via": "pending_review"},
    )
    await _apply_action(
        context, db, cfg, chat_id=chat_id, chat_title=None,
        user_id=user_id, username=None, message_id=msg_id,
        decision=decision, original_text=text,
        first_name=(seen["first_name"] if seen else None),
    )
    if public_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=public_id)
        except TelegramError:
            pass
    try:
        await q.edit_message_text(
            f"{q.message.text_html or q.message.text}{t('hdl.review_spam_suffix')}",
            parse_mode="HTML", disable_web_page_preview=True,
        )
    except TelegramError:
        pass
    await q.answer(t("hdl.review_spam_toast"))


async def _moderate_bot_message(context, db, cfg, msg, user) -> None:
    """Modera un mensaje de un BOT externo miembro del grupo. Si tiene botones
    inline (spam típico) o URL en blocklist → ban federado del bot + delete.
    Silencioso (auto-ban). Los bots legítimos sin spam no disparan nada."""
    hits = []
    # OJO: NO se usa buttons_det aquí. Los botones inline son señal de spam cuando
    # los manda un HUMANO (no puede crearlos: implica forward de canal promocional),
    # pero en un BOT son su forma normal de trabajar. Aplicarlo a bots baneaba a
    # bots de moderación legítimos: caso real, @MissRose_bot expulsada de 4 grupos
    # por publicar su aviso de warn, que lleva un botón, tras 685 mensajes buenos.
    # Para un bot solo cuentan señales de spam REAL:
    hits.append(url_det.check(msg, cfg.url_blocklist, is_first_msg=True))
    hits.append(comad_det.check(msg, is_first_msg=True))
    real = [h for h in hits if h]
    if not real:
        return
    rule = "+".join(h.rule for h in real)
    score = sum(h.score for h in real)
    log.info("BOT spam user=%s (@%s) chat=%s reglas=%s → ban directo",
             user.id, user.username, msg.chat_id, rule)
    decision = Decision(
        action="ban", score=score, rule=real[0].rule,
        reason=t("reason.external_bot_spam", rules=rule),
        payload={"is_bot": True, "rules": [h.rule for h in real]},
    )
    await _apply_action(
        context, db, cfg, chat_id=msg.chat_id, chat_title=msg.chat.title,
        user_id=user.id, username=user.username, message_id=msg.message_id,
        decision=decision, original_text=(msg.text or msg.caption),
        first_name=user.first_name,
    )


async def _moderate_channel_message(context, db, cfg, msg) -> None:
    """Modera un mensaje publicado EN NOMBRE DE UN CANAL (sender_chat) en un grupo
    de discusión/comentarios. Solo actúa ante reglas FUERTES (botones inline, URL en
    blocklist, anuncio comercial): banea al canal con banChatSenderChat + borra.

    Se descartan antes (no son spam):
      - el post auto-reenviado que encabeza el hilo de comentarios (is_automatic_forward),
      - los admins anónimos, que postean "como el propio grupo" (sender_chat == chat).
    Falsos positivos > negativos: un canal legítimo que comente sin disparar reglas
    fuertes no se toca.
    """
    sc = getattr(msg, "sender_chat", None)
    if sc is None:
        return
    if getattr(msg, "is_automatic_forward", False):
        return  # post del canal vinculado que abre el hilo: legítimo
    if sc.id == msg.chat_id:
        return  # admin anónimo del grupo posteando "como el grupo"
    if msg.chat.type in ("group", "supergroup"):
        await _ensure_chat_registered(context, db, msg.chat)
    if not cfg.is_moderated(msg.chat_id):
        return
    hits = [
        buttons_det.check(msg),
        url_det.check(msg, cfg.url_blocklist, is_first_msg=True),
        comad_det.check(msg, is_first_msg=True),
        contact_det.check(msg, _chat_allowed_scripts(db, msg.chat_id, cfg),
                              cfg.non_latin_ratio_threshold),
    ]
    real = [h for h in hits if h]
    if not real:
        return
    rule = "channel_sender+" + "+".join(h.rule for h in real)
    score = sum(h.score for h in real)
    sc_name = sc.title or (f"@{sc.username}" if sc.username else str(sc.id))
    mode = "shadow" if cfg.shadow else "active"
    log.info("CHANNEL spam sender_chat=%s (%s) chat=%s reglas=%s → ban canal (%s)",
             sc.id, sc_name, msg.chat_id, rule, mode)
    if not cfg.shadow:
        try:
            await context.bot.ban_chat_sender_chat(chat_id=msg.chat_id, sender_chat_id=sc.id)
        except TelegramError as exc:
            log.warning("ban_chat_sender_chat fallo chat=%s sc=%s: %s", msg.chat_id, sc.id, exc)
        try:
            await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
        except TelegramError as exc:
            log.debug("delete channel-sender msg fallo: %s", exc)
    db.log_action(
        chat_id=msg.chat_id, user_id=sc.id, username=(sc.username or None),
        message_id=msg.message_id, rule=rule, action="ban", score=score, mode=mode,
        payload={"sender_chat": True, "title": sc.title, "rules": [h.rule for h in real]},
    )
    if cfg.admin_notify_chat_id:
        prefix = t("hdl.shadow_prefix") if cfg.shadow else ""
        try:
            await context.bot.send_message(
                chat_id=cfg.admin_notify_chat_id,
                text=t(
                    "hdl.channel_banned",
                    prefix=prefix,
                    chat=_h.escape(msg.chat.title or str(msg.chat_id)),
                    channel=_h.escape(sc_name),
                    channel_id=sc.id,
                    rule=_h.escape(rule),
                ),
                parse_mode="HTML", disable_web_page_preview=True,
            )
        except TelegramError:
            pass


async def _moderate_via_bot_message(context, db, cfg, msg, user) -> bool:
    """Mensaje posteado por un user VÍA inline bot. Si tiene botones spam,
    borra el mensaje y avisa al admin (NO autobanea al user: puede ser
    establecido y haber sido engañado). Devuelve True si actuó."""
    bhit = buttons_det.check(msg)
    if not bhit:
        return False
    via = getattr(msg, "via_bot", None)
    via_uname = getattr(via, "username", None) if via else None
    # Borrar el mensaje
    try:
        await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
    except TelegramError as exc:
        log.debug("via_bot delete fallo: %s", exc)
    db.log_action(
        chat_id=msg.chat_id, user_id=user.id, username=user.username,
        message_id=msg.message_id, rule="via_bot_spam", action="delete",
        score=bhit.score, mode=("shadow" if cfg.shadow else "active"),
        payload={"via_bot": via_uname},
    )
    # Avisar al admin (DM) con perfil clicable, para que decida sobre el user
    if cfg.admin_notify_chat_id:
        display = _h.escape(user.first_name or str(user.id))
        try:
            await context.bot.send_message(
                chat_id=cfg.admin_notify_chat_id,
                text=t(
                    "hdl.via_bot_deleted",
                    chat=msg.chat.title or msg.chat_id,
                    uid=user.id,
                    name=display,
                    via_bot=via_uname or "?",
                    n_buttons=bhit.payload.get("n_buttons", "?"),
                ),
                parse_mode="HTML", disable_web_page_preview=True,
            )
        except TelegramError:
            pass
    return True


def _antiflood_threshold(
    context: ContextTypes.DEFAULT_TYPE, db: DB, chat_id: int, user_id: int,
) -> int:
    """Mensajes en la ventana que cuentan como flood. Base configurable; veteranos
    y humanos confirmados por el admin tienen más margen (base+4 y base+6)."""
    cfg: Config = context.bot_data["cfg"]
    base = cfg.flood_max_msgs
    if db.flood_is_human_confirmed(chat_id, user_id):
        return base + 6  # el admin ya dijo "no es bot" → más libertad
    trust = _trust_score_cached(context, db, chat_id, user_id)
    return base + 4 if trust >= 70 else base


def _antiflood_check(
    context: ContextTypes.DEFAULT_TYPE, db: DB, chat_id: int, user_id: int,
) -> bool:
    """True si el user supera su umbral de mensajes en la ventana configurada."""
    cfg: Config = context.bot_data["cfg"]
    window_s = float(cfg.flood_window_s)
    threshold = _antiflood_threshold(context, db, chat_id, user_id)
    log_store = context.bot_data.setdefault("_flood_log", {})
    key = (chat_id, user_id)
    now = time.time()
    if len(log_store) > 5000:
        stale = [k for k, h in log_store.items() if not h or h[-1] < now - window_s]
        for k in stale:
            log_store.pop(k, None)
    history = log_store.get(key)
    if history is None:
        history = deque(maxlen=50)
        log_store[key] = history
    while history and history[0] < now - window_s:
        history.popleft()
    history.append(now)
    if len(history) < threshold:
        return False
    # Anti-doble-disparo: si ya se actuó hace <60s (mismo burst), no repetir
    last_action = context.bot_data.setdefault("_flood_last_action", {})
    if len(last_action) > 5000:
        for k in [k for k, t in last_action.items() if t < now - 600]:
            last_action.pop(k, None)
    if last_action.get(key, 0) > now - 60:
        return False
    last_action[key] = now
    return True


async def _antiflood_apply(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int, user_id: int, user, msg_id: int,
) -> None:
    """Mute 6h por flood + aviso público con motivo + (1ª vez) botón es/no-bot al admin."""
    db: DB = context.bot_data["db"]
    cfg: Config = context.bot_data["cfg"]
    # GUARD: nunca antiflood a admin del chat
    if await _is_admin_of_chat(context, chat_id, user_id):
        return
    from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
    mute_hours = cfg.flood_mute_hours
    now = time.time()
    until = int(now) + mute_hours * 3600
    if not cfg.shadow:
        # Un mute sobre alguien EXPULSADO lo DEVUELVE al grupo como restringido.
        # En una ráfaga de flood es fácil que otra regla ya lo haya baneado antes
        # de que llegue este mute, y entonces el mute deshace el ban en silencio.
        if not await verification.restringir_seguro(
                context.bot, db, chat_id, user_id,
                ChatPermissions(can_send_messages=False), "antiflood",
                until_date=until):
            return
    mute_count, review_sent, human_confirmed = db.flood_record_mute(chat_id, user_id, now)
    db.log_action(
        chat_id=chat_id, user_id=user_id, username=getattr(user, "username", None),
        message_id=msg_id, rule="antiflood", action="mute",
        score=50, mode=("shadow" if cfg.shadow else "active"),
        payload={"window_s": cfg.flood_window_s, "mute_hours": mute_hours, "mute_count": mute_count},
    )
    name = _h.escape((getattr(user, "first_name", None) or str(user_id))[:40])
    # Aviso público con motivo (autoborra 1h)
    try:
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=t("hdl.flood_muted_public", name=name, hours=mute_hours),
            parse_mode="HTML", disable_notification=True,
        )
        jq = context.application.job_queue
        if jq is not None and sent is not None:
            jq.run_once(
                borrado_diferido.borrar_mensaje_job, when=3600,
                data={"chat_id": chat_id, "message_id": sent.message_id},
                name=f"del_antiflood_{chat_id}_{sent.message_id}",
            )
    except TelegramError:
        pass
    # Botón al admin SOLO la 1ª vez (reincidencia → re-mute sin preguntar).
    if review_sent or human_confirmed:
        return
    admin_dm = cfg.admin_notify_chat_id
    if not admin_dm:
        return
    user_link = f'<a href="tg://user?id={user_id}">{name}</a>'
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(t("hdl.btn.not_bot"), callback_data=f"flood:human:{chat_id}:{user_id}"),
        InlineKeyboardButton(t("hdl.btn.is_bot"), callback_data=f"flood:bot:{chat_id}:{user_id}"),
    ]])
    try:
        await context.bot.send_message(
            chat_id=admin_dm,
            text=t(
                "hdl.flood_detected_dm",
                user_link=user_link, uid=user_id, chat_id=chat_id, hours=mute_hours,
            ),
            parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True,
        )
        db.flood_mark_review_sent(chat_id, user_id)
    except TelegramError as exc:
        log.debug("antiflood admin prompt fallo: %s", exc)


async def on_flood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Botones del aviso de flood: «No es bot» (margen + unmute) / «Es bot» (ban)."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("flood:"):
        return
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    if not query.from_user or query.from_user.id != cfg.admin_user_id:
        await query.answer(t("hdl.only_bot_admin"), show_alert=True)
        return
    parts = query.data.split(":")
    if len(parts) != 4:
        await query.answer()
        return
    _, verdict, chat_id_s, user_id_s = parts
    chat_id, user_id = int(chat_id_s), int(user_id_s)
    base = query.message.text_html if query.message else ""
    if verdict == "human":
        db.flood_confirm_human(chat_id, user_id)
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id, user_id=user_id,
                permissions=verification.VERIFIED_PERMISSIONS,
            )
        except TelegramError as exc:
            log.debug("flood unmute fallo user=%s: %s", user_id, exc)
        invalidate_trust_cache(context, chat_id, user_id)
        await query.answer(t("hdl.flood_human_toast"))
        try:
            await query.edit_message_text(
                base + t("hdl.flood_human_suffix"),
                parse_mode="HTML",
            )
        except TelegramError:
            pass
    elif verdict == "bot":
        await _apply_action(
            context, db, cfg, chat_id=chat_id, chat_title=None,
            user_id=user_id, username=None, message_id=None,
            decision=Decision(action="ban", score=200, rule="flood_confirmed_bot",
                              reason=t("reason.flood_confirmed_bot"), payload={}),
            original_text=None, first_name=None,
        )
        await query.answer(t("hdl.flood_banned_toast"))
        try:
            await query.edit_message_text(
                base + t("hdl.flood_banned_suffix"),
                parse_mode="HTML",
            )
        except TelegramError:
            pass
    else:
        await query.answer()


async def _safe_cleanup_consecutive(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, banned_user_id: int,
    banned_msg_id: int | None, banned_msg_ts: float | None = None,
) -> None:
    """Wrapper que captura excepciones del cleanup en background.

    Sin esto, una excepción dentro del task lanzado con `create_task` se traga
    silenciosamente (no hay await) y queda como Future con exception unhandled.
    """
    try:
        await _cleanup_consecutive_after_ban(
            context, chat_id=chat_id, banned_user_id=banned_user_id,
            banned_msg_id=banned_msg_id, banned_msg_ts=banned_msg_ts,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "cleanup_consecutive task falló user=%s chat=%s: %s",
            banned_user_id, chat_id, exc,
        )


async def _cleanup_consecutive_after_ban(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, banned_user_id: int,
    banned_msg_id: int | None, banned_msg_ts: float | None = None,
    max_probe: int = 8, delay_s: float = 2.5,
) -> int:
    """Tras un ban, sondea msg_ids consecutivos al baneado usando SOLO Bot API.

    Usa `forwardMessage` al admin DM como sonda. La response incluye `forward_origin`
    con el sender del msg en el chat fuente. Si coincide con el baneado, borra del chat.
    Siempre limpia el sondeo del admin DM (no spammea).

    LIMITACIÓN conocida: si el msg consecutivo es un forward desde canal/bot,
    Telegram preserva en la cadena solo el ORIGEN ÚLTIMO (canal), no el intermediario
    (baneado). En esos casos no se puede confirmar sender y NO se actúa (conservador).
    Para esos forwards, el detector `forward_first_msg` actúa en el primer mensaje, así
    que rara vez llegan a esta situación.
    """
    if banned_msg_id is None:
        return 0
    cfg = context.bot_data["cfg"]
    admin_dm = cfg.admin_notify_chat_id
    # Guard: evitar loops (sondear al propio bot o a chat <=0 sería absurdo)
    if not admin_dm or admin_dm <= 0 or admin_dm == context.bot.id:
        log.debug("cleanup_consecutive skip: admin_dm inválido (%s)", admin_dm)
        return 0
    # Cap por hora para no provocar FloodWait al admin_dm (8 probes × N bans/hora puede ser mucho)
    cleanup_log = context.bot_data.setdefault("_cleanup_consecutive_log", deque(maxlen=200))
    now = time.time()
    while cleanup_log and cleanup_log[0] < now - 3600:
        cleanup_log.popleft()
    if len(cleanup_log) >= 50:  # max 50 cleanups/hora (= 400 forwards/hora máx)
        log.warning("cleanup_consecutive rate-limit hora alcanzado, skip user=%s", banned_user_id)
        return 0
    cleanup_log.append(now)
    await asyncio.sleep(delay_s)
    deleted = 0
    consecutive_misses = 0
    for i in range(1, max_probe + 1):
        if i > 1:
            await asyncio.sleep(0.3)  # suavizar ráfaga, evita FloodWait
        probe_id = banned_msg_id + i
        try:
            sent = await context.bot.forward_message(
                chat_id=admin_dm, from_chat_id=chat_id,
                message_id=probe_id, disable_notification=True,
            )
        except TelegramError as exc:
            if "not found" in str(exc).lower():
                consecutive_misses += 1
                if consecutive_misses >= 3:
                    break
                continue
            log.debug("cleanup_consecutive probe %s exc: %s", probe_id, exc)
            continue
        consecutive_misses = 0
        # Identificar sender en el chat fuente vía forward_origin
        sender_id: int | None = None
        origin = getattr(sent, "forward_origin", None)
        if origin is not None:
            su = getattr(origin, "sender_user", None)
            sc = getattr(origin, "sender_chat", None)
            if su is not None:
                sender_id = su.id
            elif sc is not None:
                sender_id = sc.id
        if sender_id is None:
            fwd_from = getattr(sent, "forward_from", None)
            if fwd_from is not None:
                sender_id = fwd_from.id
        should_delete = False
        delete_reason = ""
        text = getattr(sent, "text", None) or getattr(sent, "caption", None) or ""

        # Caso 1: sender confirmado == baneado
        if sender_id == banned_user_id:
            should_delete = True
            delete_reason = "sender confirmado"
        # Para los siguientes casos, nunca borrar si es del propio bot
        elif sender_id == context.bot.id:
            pass
        else:
            # Caso 2: tiene botones inline (reply_markup). Usuarios normales no
            # pueden enviar reply_markup, solo canales/bots. Forward de spam casi seguro.
            rm = getattr(sent, "reply_markup", None)
            has_buttons = bool(rm and getattr(rm, "inline_keyboard", None))
            if has_buttons:
                should_delete = True
                delete_reason = "msg con botones inline (forward de canal/bot)"
            # Caso 3: forward en ventana temporal corta del ban. Cubre canal,
            # chat o user-bot. Para "user" requerimos que sea bot (no humano random).
            elif banned_msg_ts is not None and origin is not None:
                origin_type = getattr(origin, "type", None)
                fwd_date = getattr(sent, "forward_date", None)
                if fwd_date is not None and origin_type in ("channel", "chat", "user"):
                    fwd_ts = fwd_date.timestamp() if hasattr(fwd_date, "timestamp") else float(fwd_date)
                    if abs(fwd_ts - banned_msg_ts) <= 30:
                        if origin_type in ("channel", "chat"):
                            should_delete = True
                            delete_reason = f"forward de canal en ventana ataque ({abs(fwd_ts - banned_msg_ts):.1f}s)"
                        else:
                            # origin_type == "user": solo si es bot (cuenta automatizada)
                            su = getattr(origin, "sender_user", None)
                            if su and getattr(su, "is_bot", False):
                                should_delete = True
                                delete_reason = f"forward de bot en ventana ataque ({abs(fwd_ts - banned_msg_ts):.1f}s)"
            # Caso 4: contenido en script no-latín dominante (>=50%). Cubre
            # msgs en chino/cirílico/etc. sin forward, en ventana temporal.
            if not should_delete and text and banned_msg_ts is not None:
                fwd_date = getattr(sent, "forward_date", None)
                ts_to_check = (
                    (fwd_date.timestamp() if hasattr(fwd_date, "timestamp") else float(fwd_date))
                    if fwd_date is not None else None
                )
                in_window = ts_to_check is not None and abs(ts_to_check - banned_msg_ts) <= 60
                # Si no hay fwd_date (msg directo), aceptamos siempre que estemos
                # en el rango consecutive_id (max_probe=8 garantiza temporal corto).
                if in_window or fwd_date is None:
                    letters = [c for c in text if c.isalpha()]
                    if len(letters) >= 5:
                        non_latin = sum(1 for c in letters if not c.isascii())
                        ratio = non_latin / len(letters)
                        if ratio >= 0.5:
                            should_delete = True
                            delete_reason = f"contenido script no-latín ({ratio:.0%})"
        if should_delete:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=probe_id)
                deleted += 1
                log.info(
                    "cleanup_consecutive borró msg=%s user=%s chat=%s (%s)",
                    probe_id, banned_user_id, chat_id, delete_reason,
                )
            except TelegramError as exc:
                log.debug("cleanup_consecutive delete fail msg=%s: %s", probe_id, exc)
        # Siempre limpiar el sondeo del admin DM (incluso si era de otro user, lo borramos)
        try:
            await context.bot.delete_message(chat_id=admin_dm, message_id=sent.message_id)
        except TelegramError:
            pass
    return deleted


async def _apply_action(
    context: ContextTypes.DEFAULT_TYPE,
    db: DB,
    cfg: Config,
    chat_id: int,
    chat_title: str | None,
    user_id: int,
    username: str | None,
    message_id: int | None,
    decision: Decision,
    original_text: str | None,
    first_name: str | None = None,
) -> None:
    mode = "shadow" if cfg.shadow else "active"

    # GUARD: nunca banear/kickear/mutear admins del propio chat
    if user_id and decision.action in ("ban", "kick", "mute") and not cfg.shadow:
        if await _is_admin_of_chat(context, chat_id, user_id):
            log.warning(
                "GUARD: %s sobre admin user=%s chat=%s rule=%s → noop",
                decision.action, user_id, chat_id, decision.rule,
            )
            decision = Decision(action="noop", score=decision.score,
                                rule=decision.rule,
                                reason=t("reason.admin_immune_prefix") + " " + decision.reason,
                                payload=decision.payload)

    action_id = db.log_action(
        chat_id=chat_id, user_id=user_id, username=username, message_id=message_id,
        rule=decision.rule, action=decision.action, score=decision.score,
        mode=mode, payload={"reason": decision.reason, **(decision.payload or {})},
    )

    # Bienvenida del baneado. La guarda es IMPRESCINDIBLE y se perdió en un refactor:
    # `_apply_action` corre con CUALQUIER decisión, también `noop`, y esta limpieza
    # borra la fila `pending_verifications` del usuario en TODOS los chats. Sin la
    # guarda, un recién llegado que saluda a los 10 s (jfm_fast = 30 puntos = noop,
    # o sea el bot NO sanciona) perdía su verificación pendiente en OTRO grupo: al
    # pulsar SOY HUMANO allí, el bot no encontraba la fila, no le quitaba el mute y
    # se quedaba mudo para siempre, invisible para el recordatorio y para el kick.
    if user_id and decision.action in ("ban", "kick") and not cfg.shadow:
        await verification.limpiar_bienvenidas(context, db, user_id)

    fed_results: dict[int, str] | None = None
    if decision.action != "noop":
        try:
            if cfg.shadow:
                log.info(
                    "[SHADOW] would %s user=%s chat=%s rule=%s score=%d reason=%s",
                    decision.action, user_id, chat_id, decision.rule, decision.score, decision.reason,
                )
                # En shadow NO actuamos, pero SÍ avisamos al canal para poder
                # EVALUAR lo que haría (marcado [SHADOW]). Es lo más útil al probar:
                # ver los "habría baneado" en Telegram en vez de en docker logs.
                if cfg.admin_notify_chat_id:
                    try:
                        if message_id:
                            await context.bot.copy_message(
                                chat_id=cfg.admin_notify_chat_id,
                                from_chat_id=chat_id, message_id=message_id,
                            )
                        display = (first_name or username or str(user_id))
                        name_link = f'<a href="tg://user?id={user_id}">{_h.escape(display)}</a>'
                        if username:
                            name_link += f" (@{username})"
                        habria = {
                            "ban": t("hdl.would.ban"),
                            "kick": t("hdl.would.kick"),
                            "mute": t("hdl.would.mute"),
                            "delete": t("hdl.would.delete"),
                        }.get(decision.action, t("hdl.would.other", action=decision.action))
                        motivo = (
                            rule_explain.explain(decision.rule)
                            or (decision.reason or "").strip()
                            or t("hdl.reason_generic")
                        )
                        await context.bot.send_message(
                            chat_id=cfg.admin_notify_chat_id,
                            text=t(
                                "hdl.shadow_notice",
                                chat=chat_title or chat_id,
                                user_link=name_link,
                                uid=user_id,
                                would=habria,
                                reason=_h.escape(motivo),
                                rule=decision.rule,
                                score=decision.score,
                            ),
                            parse_mode="HTML", disable_web_page_preview=True,
                        )
                    except TelegramError as exc:
                        log.debug("shadow notify fallo: %s", exc)
            else:
                # Reportar oficialmente a Telegram ANTES del ban — SOLO si:
                #   - decision.action == "ban" (kick es recuperable, no merece reporte permanente)
                #   - alguna regla disparada está en whitelist de alta confianza
                #   - decision.score >= REPORT_MIN_SCORE (combinación clara, no borderline)
                # Esto evita penalizar el "trust" de la cuenta Telethon como reporter en Native Antispam.
                if decision.action == "ban" and _is_reportable(decision):
                    reporter = context.bot_data.get("reporter")
                    if reporter is not None and reporter.reporting_ready():
                        reason_kind = "fake" if decision.rule == "cas_match" else "spam"
                        reporter.enqueue(
                            chat_id=chat_id, user_id=user_id,
                            message_id=message_id, reason=reason_kind,
                            detail=f"[{decision.rule}] {decision.reason}",
                        )
                # Delete primero (si hay message_id y permiso)
                # ORDEN OPTIMIZADO para minimizar ventana de race del spammer:
                # 1) BAN primero (corta upstream a Telegram lo antes posible — sin
                #    esto, msgs "en vuelo" del spammer se cuelan antes de propagarse).
                # 2) Copy a admin DM + delete del msg en chat público.
                # 3) Cleanup retrospectivo de la ráfaga.
                banned_msg_ts = time.time()
                if decision.action == "ban":
                    if cfg.federation_enabled:
                        fed_results = await federate_ban(
                            context.bot, db, user_id=user_id,
                            reason=decision.reason, rule=decision.rule,
                            triggered_in_chat=chat_id, shadow=False,
                        )
                    else:
                        await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                elif decision.action == "kick":
                    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                    await asyncio.sleep(0.5)
                    await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)

                # Copy a admin DM + delete del msg (después del ban)
                if message_id and decision.action in ("ban", "kick", "mute", "delete"):
                    action_label = "ban" if decision.action in ("ban", "kick") else "delete"
                    db.mark_admin_report_action(chat_id, message_id, action_label)
                    if cfg.admin_notify_chat_id:
                        try:
                            await context.bot.copy_message(
                                chat_id=cfg.admin_notify_chat_id,
                                from_chat_id=chat_id,
                                message_id=message_id,
                            )
                            # Perfil clicable (es DM privado al admin, sin riesgo de visibilidad)
                            display = (first_name or username or str(user_id))
                            name_link = f'<a href="tg://user?id={user_id}">{_h.escape(display)}</a>'
                            if username:
                                name_link += f" (@{username})"
                            accion = {
                                "ban": t("hdl.act.ban"),
                                "kick": t("hdl.act.kick"),
                                "mute": t("hdl.act.mute"),
                                "delete": t("hdl.act.delete"),
                            }.get(decision.action, t("hdl.act.other", action=decision.action))
                            # Motivo comprensible SIEMPRE: explicación mapeada →
                            # si la regla no está en el mapa, la razón del propio
                            # detector → y si tampoco, un genérico. Nunca vacío.
                            motivo = (
                                rule_explain.explain(decision.rule)
                                or (decision.reason or "").strip()
                                or t("hdl.reason_generic")
                            )
                            motivo_line = t("hdl.reason_line", reason=_h.escape(motivo))
                            await context.bot.send_message(
                                chat_id=cfg.admin_notify_chat_id,
                                text=t(
                                    "hdl.action_notice",
                                    chat=chat_title or chat_id,
                                    user_link=name_link,
                                    uid=user_id,
                                    action=accion,
                                    reason_line=motivo_line,
                                    rule=decision.rule,
                                    score=decision.score,
                                ),
                                parse_mode="HTML",
                                disable_web_page_preview=True,
                            )
                        except TelegramError as exc:
                            log.debug("copy_message a admin DM fallo: %s", exc)
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except TelegramError as exc:
                        log.warning("delete_message fallo: %s", exc)

                # Cleanup retrospectivo solo para ban/kick (no para mute/delete simples)
                if decision.action in ("ban", "kick"):
                    context.application.create_task(
                        _safe_cleanup_consecutive(
                            context, chat_id=chat_id, banned_user_id=user_id,
                            banned_msg_id=message_id, banned_msg_ts=banned_msg_ts,
                        ),
                        update=None,
                    )

                if decision.action == "mute":
                    from telegram import ChatPermissions
                    # Mismo motivo que en el antiflood: si el usuario ya está
                    # baneado, este mute lo devolvería al grupo.
                    await verification.restringir_seguro(
                        context.bot, db, chat_id, user_id,
                        ChatPermissions(can_send_messages=False), "acción mute",
                        until_date=int(time.time()) + 24 * 3600,
                    )
                # delete ya hecho arriba
        except TelegramError as exc:
            log.error("Acción %s falló: %s", decision.action, exc)

    # En modo shadow, simular resultados federados para que la notificación
    # muestre cuántos chats SE habrían afectado.
    if cfg.shadow and decision.action == "ban" and cfg.federation_enabled:
        fed_results = await federate_ban(
            context.bot, db, user_id=user_id, reason=decision.reason,
            rule=decision.rule, triggered_in_chat=chat_id, shadow=True,
        )

    # Quip público al banear/kick. HÍBRIDO: por defecto los bans AUTOMÁTICOS
    # (detectores) son silenciosos; el quip solo se publica en bans manuales
    # del admin (cmd_ban/cmd_spam, que no pasan por aquí). Toggle con
    # QUIP_ON_AUTO_BAN=true si se quiere también quip en auto-bans.
    if (
        quips.quips_on(db, chat_id, cfg)
        and cfg.quip_on_auto_ban
        and not cfg.shadow
        and decision.action in ("ban", "kick")
    ):
        quip = quips.pick(
            rule=decision.rule, username=username, user_id=user_id,
            payload=decision.payload or {}, first_name=first_name,
        )
        if quip:
            from . import ban_announce
            await ban_announce.announce_ban(
                context, chat_id=chat_id, quip_text=quip,
                delete_after=cfg.public_quip_delete_after_s,
            )

    notifier: Notifier = context.bot_data["notifier"]
    if notifier.is_configured():
        session = context.bot_data.get("http")
        if session is None:
            log.debug("notifier: http session no inicializada, saltando alerta")
            return
        # Enriquece con señales del perfil (fotos, edad cuenta, bio) via Telethon
        signals_markup = ""
        reporter = context.bot_data.get("reporter")
        client = reporter.get_client() if reporter else None
        if client is not None and user_id:
            try:
                sig = await user_signals.fetch(client, user_id, chat_id=chat_id)
                signals_markup = user_signals.render_markup(sig)
            except Exception as exc:
                log.debug("user_signals fallo user=%s: %s", user_id, exc)
        await notifier.send_action_alert(
            session=session, action_id=action_id,
            chat_title=chat_title, chat_id=chat_id,
            user_id=user_id, username=username,
            action=decision.action, rule=decision.rule,
            reason=decision.reason, score=decision.score,
            original_text=original_text, mode=mode,
            federation_results=fed_results,
            user_signals_markup=signals_markup,
        )




async def _avisar_readmision(context, cfg, cmu, objetivo) -> None:
    """Avisa de que otro admin readmitió a alguien que estaba baneado.

    Con botón para aceptar su decisión: si el otro admin tenía razón, levantar el
    ban de verdad (quitarlo de la lista federada) en vez de dejar al bot y a la
    persona peleándose cada vez que escriba.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    destino = cfg.admin_notify_chat_id or cfg.admin_user_id
    if not destino:
        return
    actor = cmu.from_user
    texto = t(
        "hdl.readmitido",
        name=_h.escape((objetivo.first_name or str(objetivo.id))[:40]),
        uid=objetivo.id,
        chat=_h.escape(str(cmu.chat.title or cmu.chat.id)),
        actor=_h.escape("@" + actor.username if actor.username else (actor.first_name or str(actor.id))),
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(t("hdl.btn.readm_keep"),
                             callback_data=f"readm:keep:{objetivo.id}"),
        InlineKeyboardButton(t("hdl.btn.readm_lift"),
                             callback_data=f"readm:lift:{objetivo.id}"),
    ]])
    try:
        await context.bot.send_message(chat_id=destino, text=texto, parse_mode="HTML",
                                       reply_markup=kb, disable_web_page_preview=True)
    except TelegramError as exc:
        log.warning("aviso de readmisión falló: %s", exc)


async def on_readmision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Botones del aviso de readmisión: mantener el ban o levantarlo de verdad."""
    q = update.callback_query
    if q is None:
        return
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer(t("hdl.only_admin_review"))
        return
    try:
        _, accion, uid_s = q.data.split(":", 2)
        user_id = int(uid_s)
    except Exception as exc:  # noqa: BLE001
        await q.answer(t("hdl.callback_invalid", error=exc))
        return

    if accion == "lift":
        # Aceptar la decisión del otro admin: fuera de la lista federada y
        # desbaneado en todos los grupos, para que deje de rebotar.
        db.revoke_ban(user_id, revoked_by=cfg.admin_user_id)
        for fila in db.all_chats():
            if not fila["am_admin"]:
                continue
            try:
                await context.bot.unban_chat_member(
                    chat_id=fila["chat_id"], user_id=user_id, only_if_banned=True)
            except TelegramError:
                pass
        await q.answer(t("hdl.readm_lifted"))
    else:
        await q.answer(t("hdl.readm_kept"))
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass
