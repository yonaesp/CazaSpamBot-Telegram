"""Barrido semanal de bios de los miembros de los grupos.

El bot mira el perfil al entrar, en el repaso de los 7 días siguientes y con el
primer mensaje. A quien entró antes que el bot, o cuya entrada no le llegó, no lo
mira nunca. En el barrido a mano del 31-oct-2026 eran 1.982 de 6.534 miembros, y
entre ellos había una red de 5 cuentas «my blog 18+» (dentro desde sep-2025) y la
quinta cuenta de la red de Helen, que entró el 29-oct sin dejar rastro (L49). Y el
perfil de un veterano tampoco se vuelve a mirar: dos cuentas con historial, calladas
desde 2019 y 2022, tenían la bio de spam porque se las habían robado (L50).

La bio solo sale de `GetFullUser`, persona a persona: listar 1.000 miembros cuesta
0,7 s, pero cada bio es una llamada a la cuenta secundaria. Por eso:
- a cada miembro se le lee como mucho una vez cada `RELECTURA_S`, y primero a quien
  el bot no tiene visto,
- como mucho `MAX_POR_PASADA` por semana y con `PAUSA_S` entre una y otra (en
  6.534 llamadas a 1-2 s hubo un solo FloodWait, de 6 s),
- un FloodWait que Telethon no espera solo (más de 60 s) corta la pasada, y lo que
  falta sigue la semana siguiente.

Lo que da positivo (`bio_spam`, o una bio en un alfabeto que el grupo no permite y
con un enlace):
- un veterano callado desde hace meses → `cuenta_robada`: ban por seguridad y aviso;
- cualquier otro → al privado con los botones de la revisión de sospechosos
  (✅ Permitir / 🔨 Banear), sin banear: son miembros de hace tiempo y no hay prisa.
Una bio con enlace privado que no llega al umbral no se da por leída: la primera
cuenta de una red se queda en 55, y si la red crece, la semana siguiente salta.
"""
from __future__ import annotations

import asyncio
import html
import logging
import time

from telegram import InlineKeyboardMarkup
from telegram.error import TelegramError

from . import cuenta_robada, destinos, enlaces, fechas, notify_prefs, verification
from .config import Config
from .db import DB
from .detectors import bio_spam
from .i18n import t

log = logging.getLogger(__name__)

# 600 lecturas a ~2 s son unos 25 minutos por semana: los 6.500 miembros de los
# cuatro grupos se leen en unas 11 semanas, por debajo de la relectura de 90 días.
MAX_POR_PASADA = 600
PAUSA_S = 2.0
RELECTURA_S = 90 * 86400


async def barrido_job(context) -> None:
    """Lee la bio de los miembros que tocan esta semana y actúa con lo que da positivo."""
    db: DB = context.bot_data["db"]
    cfg: Config = context.bot_data["cfg"]
    reporter = context.bot_data.get("reporter")
    client = reporter.get_client() if reporter else None
    if client is None:
        log.warning("barrido_bios: sin Telethon no se puede leer ninguna bio")
        return
    try:
        r = await barrer(context, db, cfg, client)
    except Exception as exc:  # noqa: BLE001 — un trabajo de fondo nunca tumba el bot
        log.warning("barrido_bios: la pasada falló: %s", exc)
        return
    log.info("barrido_bios: %d bios leídas, %d avisos, %d cuentas robadas, %d pendientes",
             r["leidas"], r["avisos"], r["robadas"], r["pendientes"])


async def barrer(context, db: DB, cfg: Config, client) -> dict[str, int]:
    """Una pasada. Devuelve cuántas bios leyó, avisos, cuentas robadas y cuántas faltan."""
    from telethon.errors import FloodWaitError
    from telethon.tl.functions.users import GetFullUserRequest
    from telethon.tl.types import ChannelParticipantsAdmins

    from .handlers import _se_modera

    chats = {f["chat_id"]: f for f in db.all_chats() if _se_modera(db, cfg, f["chat_id"])}
    leidas_hace_poco = db.bios_barridas(time.time() - RELECTURA_S)
    admins: set[int] = set()
    cola: dict[int, tuple[list[int], object]] = {}
    for chat_id in chats:
        try:
            async for a in client.iter_participants(chat_id, filter=ChannelParticipantsAdmins()):
                admins.add(a.id)
            async for u in client.iter_participants(chat_id):
                if u.bot or u.deleted or u.is_self or u.id in leidas_hace_poco:
                    continue
                cola.setdefault(u.id, ([], u))[0].append(chat_id)
        except Exception as exc:  # noqa: BLE001 — un grupo ilegible no para los demás
            log.warning("barrido_bios: no se pudo listar chat=%s: %s", chat_id, exc)
    conocidos = db.usuarios_conocidos()
    pendientes = [(uid, cids, u) for uid, (cids, u) in cola.items()
                  if uid not in admins and not db.is_banned(uid)
                  and not db.is_whitelisted(cids[0], uid)]
    pendientes.sort(key=lambda p: p[0] in conocidos)  # primero a quien el bot no conoce

    r = {"leidas": 0, "avisos": 0, "robadas": 0}
    for uid, cids, u in pendientes[:MAX_POR_PASADA]:
        try:
            full = await client(GetFullUserRequest(u))
        except FloodWaitError as exc:
            log.warning("barrido_bios: FloodWait de %d s tras %d bios; sigue la semana que viene",
                        exc.seconds, r["leidas"])
            break
        except Exception as exc:  # noqa: BLE001 — sin apuntarla, se reintenta la semana que viene
            log.debug("barrido_bios: no se pudo leer a %s: %s", uid, exc)
            continue
        r["leidas"] += 1
        bio = full.full_user.about or ""
        positivo = _positivo(db, cfg, cids[0], uid, bio) if bio else None
        if positivo:
            score, motivo = positivo
            msgs, warns = db.historial(uid)
            if uid in conocidos and cuenta_robada.es_veterano(db, uid):
                ultimo = await _ultimo_mensaje(client, db, cids, u)
                if ultimo is not None and time.time() - ultimo >= cuenta_robada.SILENCIO_MIN_S:
                    await cuenta_robada.expulsar(context, db, cfg, chats[cids[0]], u, bio, motivo,
                                                 score, msgs, ultimo)
                    r["robadas"] += 1
                else:
                    contexto = (t("barrido.nota_activo", msgs=msgs, ultimo=fechas.dia(ultimo))
                                if ultimo else t("barrido.nota_sin_historial", msgs=msgs))
                    await _avisar(context.bot, db, cfg, chats[cids[0]], u, bio, score, motivo,
                                  contexto)
                    r["avisos"] += 1
            else:
                if uid not in conocidos:
                    contexto = t("barrido.desconocido")
                elif warns:
                    contexto = t("barrido.con_warns", msgs=msgs, warns=warns)
                else:
                    contexto = t("barrido.pocos_mensajes", msgs=msgs)
                await _avisar(context.bot, db, cfg, chats[cids[0]], u, bio, score, motivo, contexto)
                r["avisos"] += 1
        if positivo or not bio_spam.enlaces_privados(bio):
            db.marcar_bio_barrida(uid)
        await asyncio.sleep(PAUSA_S)
    r["pendientes"] = len(pendientes) - r["leidas"]
    return r


def _positivo(db: DB, cfg: Config, chat_id: int, uid: int, bio: str) -> tuple[int, str] | None:
    """(puntos, motivo) si la bio es de spam: `bio_spam`, o escrita en un alfabeto que el
    grupo no permite y con un enlace (la de «付费广告» no llegaba a 60 en `bio_spam`)."""
    hit = bio_spam.check(bio, db=db, user_id=uid)
    if hit:
        return hit.score, hit.reason
    # Sin los enlaces, que son latinos y bajarían la proporción (igual que en `bio_spam`).
    sin_urls = destinos.sin_enlaces(bio)
    otro = verification._texto_en_otro_alfabeto(
        sin_urls, verification.allowed_scripts_de(db, chat_id, cfg))
    if otro and sin_urls != bio:
        return 60, t("reason.bio_alfabeto_enlace", alfabeto=otro[0])
    return None


async def _ultimo_mensaje(client, db: DB, cids: list[int], u) -> float | None:
    """El último mensaje en cualquiera de sus grupos; None si no se pudo saber en alguno."""
    ultimo = 0.0
    for cid in cids:
        ts = await cuenta_robada.ultimo_mensaje_ts(client, db, cid, u)
        if ts is None:
            return None
        ultimo = max(ultimo, ts)
    return ultimo


async def _avisar(bot, db: DB, cfg: Config, chat, u, bio: str, score: int, motivo: str,
                  contexto: str) -> None:
    """Privado al admin con la bio, el motivo y los botones de la revisión de sospechosos."""
    chat_id = chat["chat_id"]
    db.log_action(
        chat_id=chat_id, user_id=u.id, username=u.username, message_id=None,
        rule="bio_spam", action="noop", score=score, mode=cfg.mode,
        payload={"bio_preview": bio[:200], "motivo": motivo, "via": "barrido_bios",
                 "would_be": "review"},
    )
    if not cfg.admin_notify_chat_id:
        return
    nombre = " ".join(p for p in (u.first_name, u.last_name) if p) or str(u.id)
    texto = t(
        "barrido.aviso_dm",
        persona=enlaces.al_perfil(u.id, html.escape(nombre), u.username),
        uid=u.id,
        grupo=enlaces.al_grupo(chat_id, html.escape(chat["title"] or str(chat_id)),
                               chat["username"]),
        contexto=contexto,
        bio=html.escape(bio[:300]),
        motivo=html.escape(motivo),
    )
    try:
        await bot.send_message(
            chat_id=cfg.admin_notify_chat_id, text=texto, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([verification._rv_decide_row(chat_id, u.id)]),
            disable_web_page_preview=True,
            disable_notification=notify_prefs.sin_sonido(db, importante=True),
        )
    except TelegramError as exc:
        log.warning("barrido_bios: no se pudo avisar de %s: %s", u.id, exc)
