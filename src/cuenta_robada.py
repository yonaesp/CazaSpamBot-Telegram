"""Cuenta robada: un veterano que lleva meses sin escribir aparece con la bio de spam.

Caso (1-nov-2026, L50): el barrido de bios encontró en Domótica dos cuentas con
historial, de 8 y 25 mensajes, calladas desde dic-2022 y dic-2019, cuya bio era ahora
«BITNEST https://bitnest.me/…» y «付费广告 https://t.me/ZOGJ001». Se las robaron a su
dueño, y quien las usa busca miembros a los que escribir por privado.

Decisión del admin: se banean en todos los grupos por seguridad (quien robó la cuenta
no puede volver a entrar) y se avisa en el grupo. Es el único caso en que puede haber
una persona real que reclame, así que el aviso dice a quién escribir. A quien nunca
escribió no se le pone aviso público: no hay a quién explicárselo. Y a quien escribe
a menudo tampoco se le banea solo: una bio con su propio canal no es una cuenta
robada, y decide el admin.

Ajustes por chat (panel ▸ Cuentas robadas y `/robadas`), NULL = defecto:
- `robada_mencion`: `dueno` (defecto), `elegidos` (el dueño y `robada_admins`) o
  `todos` los admins humanos del grupo.
- `robada_privado`: 1 (defecto), los mencionados reciben el aviso por privado con
  «Bien baneada» / «Desbanear»; 0, solo el dueño, que siempre se entera.
"""
from __future__ import annotations

import html
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import destinos, enlaces, fechas, notify_prefs, permissions, settings_sync
from .config import Config
from .db import DB
from .i18n import t

log = logging.getLogger(__name__)

# «Meses sin escribir»: por debajo, quien escribe a menudo y se pone su canal en la bio.
SILENCIO_MIN_S = 90 * 86400
# El aviso del grupo es para que los miembros no hagan caso a sus privados: un día basta.
AVISO_TTL_S = 24 * 3600
MENCIONES = ("dueno", "elegidos", "todos")
PREFIX = "robada"


def mencion_de(s) -> str:
    try:
        v = (s["robada_mencion"] or "dueno").lower()
    except (KeyError, IndexError, TypeError):
        return "dueno"
    return v if v in MENCIONES else "dueno"


def privado_de(s) -> bool:
    try:
        return s["robada_privado"] is None or bool(s["robada_privado"])
    except (KeyError, IndexError, TypeError):
        return True


def elegidos_de(s) -> list[int]:
    try:
        crudo = s["robada_admins"] or ""
    except (KeyError, IndexError, TypeError):
        return []
    return [int(x) for x in crudo.split(",") if x.strip().lstrip("-").isdigit()]


def es_veterano(db: DB, user_id: int) -> bool:
    """Ha escrito antes y nunca le han puesto un warn."""
    from .verification import MIN_MSGS_DE_CASA
    msgs, warns = db.historial(user_id)
    return msgs >= MIN_MSGS_DE_CASA and warns == 0


async def ultimo_mensaje_ts(client, db: DB, chat_id: int, usuario) -> float | None:
    """Cuándo escribió por última vez. 0.0 = en este grupo, nunca; None = no se sabe.

    Primero la base; si no lo sabe o es viejo, se pregunta a Telegram (una llamada, y
    solo para quien ya ha dado positivo): la mayoría de los veteranos se importaron del
    historial y no tienen `last_msg_ts`.
    """
    ts = db.ultimo_mensaje_ts(usuario.id) or 0.0
    if ts and time.time() - ts < SILENCIO_MIN_S:
        return ts
    try:
        async for m in client.iter_messages(chat_id, from_user=usuario, limit=5):
            if m.action is None:
                return max(ts, m.date.timestamp())
        return ts
    except Exception as exc:  # noqa: BLE001 — sin saberlo no se banea a un veterano
        log.debug("cuenta_robada: no se pudo leer el historial de %s: %s", usuario.id, exc)
        return None


async def _mencion(bot, chat_id: int, user_id: int) -> str | None:
    """El @ de un admin, o su nombre enlazado (en su grupo, `tg://user` funciona)."""
    try:
        u = (await bot.get_chat_member(chat_id=chat_id, user_id=user_id)).user
    except TelegramError:
        return None
    if u.username:
        return f"@{u.username}"
    return enlaces.al_perfil(u.id, html.escape(u.first_name or str(u.id)))


async def destinatarios(bot, db: DB, cfg: Config, chat_id: int) -> list[tuple[int, str]]:
    """(user_id, mención) de quien se menciona en el aviso, el dueño primero."""
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    modo = mencion_de(s)
    ids = [cfg.admin_user_id] if cfg.admin_user_id else []
    if modo == "elegidos":
        ids += [i for i in elegidos_de(s) if i not in ids]
    elif modo == "todos":
        try:
            for a in await bot.get_chat_administrators(chat_id):
                if not a.user.is_bot and not getattr(a, "is_anonymous", False) and a.user.id not in ids:
                    ids.append(a.user.id)
        except TelegramError as exc:
            log.debug("cuenta_robada: sin lista de admins de %s: %s", chat_id, exc)
    salida = []
    for uid in ids:
        m = await _mencion(bot, chat_id, uid)
        if m:
            salida.append((uid, m))
    return salida


async def expulsar(context, db: DB, cfg: Config, chat, usuario, bio: str, motivo: str,
                   score: int, msgs: int, ultimo_ts: float) -> None:
    """Ban federado por seguridad, aviso en el grupo y privado a quien toque."""
    from .federation import federate_ban
    bot = context.bot
    chat_id = chat["chat_id"]
    nombre = " ".join(p for p in (usuario.first_name, usuario.last_name) if p) or str(usuario.id)
    desde = fechas.dia(ultimo_ts) if ultimo_ts else t("robada.nunca")
    reason = t("reason.cuenta_robada", msgs=msgs, desde=desde, motivo=motivo)
    res = await federate_ban(bot, db, usuario.id, reason=reason, rule="cuenta_robada",
                             triggered_in_chat=chat_id, shadow=cfg.shadow)
    ok = sum(1 for v in res.values() if v in ("ok", "shadow"))
    db.log_action(
        chat_id=chat_id, user_id=usuario.id, username=usuario.username, message_id=None,
        rule="cuenta_robada", action="ban", score=score, mode=cfg.mode,
        payload={"bio_preview": bio[:200], "msgs": msgs, "ultimo_msg_ts": ultimo_ts,
                 "motivo": motivo, "via": "barrido_bios"},
    )
    if not cfg.shadow:
        destinos.aprender_de_ban(db, usuario.id, bio, "cuenta_robada")
    gente = await destinatarios(bot, db, cfg, chat_id)
    admins = ", ".join(m for _, m in gente)
    publicado = False
    if not cfg.shadow and admins:
        publicado = await _aviso_grupo(context, chat_id, nombre, usuario.id, admins)
    s = db.get_chat_settings(chat_id)
    a_quien = [uid for uid, _ in gente] if privado_de(s) else []
    if cfg.admin_notify_chat_id and cfg.admin_notify_chat_id not in a_quien:
        a_quien.insert(0, cfg.admin_notify_chat_id)
    texto = t(
        "robada.aviso_dm",
        persona=enlaces.al_perfil(usuario.id, html.escape(nombre), usuario.username),
        uid=usuario.id,
        grupo=enlaces.al_grupo(chat_id, html.escape(chat["title"] or str(chat_id)), chat["username"]),
        msgs=msgs, ultimo=desde, bio=html.escape(bio[:300]), motivo=html.escape(motivo), n=ok,
        aviso=t("robada.dm_con_aviso", admins=admins) if publicado else t("robada.dm_sin_aviso"),
    )
    await _avisar_admins(bot, db, a_quien, texto, chat_id, usuario.id)


async def _aviso_grupo(context, chat_id: int, nombre: str, uid: int, admins: str) -> bool:
    """El aviso público. Sin enlace al perfil (regla 6): nombre e id."""
    from . import borrado_diferido
    try:
        m = await context.bot.send_message(
            chat_id=chat_id, parse_mode="HTML", disable_notification=True,
            text=t("robada.aviso_grupo", nombre=html.escape(nombre), uid=uid, admins=admins),
        )
    except TelegramError as exc:
        log.warning("cuenta_robada: no se pudo avisar en %s: %s", chat_id, exc)
        return False
    borrado_diferido.programar(context, chat_id, m.message_id, AVISO_TTL_S,
                               nombre=f"del_robada_{chat_id}_{m.message_id}")
    return True


async def _avisar_admins(bot, db: DB, a_quien: list[int], texto: str,
                         chat_id: int, uid: int) -> None:
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(t("robada.btn_ok"), callback_data=f"{PREFIX}:ok:{chat_id}:{uid}"),
        InlineKeyboardButton(t("robada.btn_unban"), callback_data=f"{PREFIX}:unban:{chat_id}:{uid}"),
    ]])
    for destino in a_quien:
        try:
            await bot.send_message(
                chat_id=destino, text=texto, parse_mode="HTML", reply_markup=kb,
                disable_web_page_preview=True,
                disable_notification=notify_prefs.sin_sonido(db, importante=True),
            )
        except TelegramError as exc:  # un admin que nunca abrió el privado del bot
            log.info("cuenta_robada: no se pudo avisar por privado a %s: %s", destino, exc)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«Bien baneada» / «Desbanear». Decide el dueño o un admin del grupo afectado."""
    from .federation import unfederate_ban
    q = update.callback_query
    if q is None or not q.data:
        return
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    try:
        _, accion, chat_s, uid_s = q.data.split(":")
        chat_id, uid = int(chat_s), int(uid_s)
    except ValueError:
        await q.answer(t("review.invalid_callback"))
        return
    if q.from_user.id != cfg.admin_user_id:
        try:
            m = await context.bot.get_chat_member(chat_id=chat_id, user_id=q.from_user.id)
            puede = m.status in ("administrator", "creator")
        except TelegramError:
            puede = False
        if not puede:
            await q.answer(t("robada.solo_admins"), show_alert=True)
            return
    quien = html.escape(q.from_user.first_name or str(q.from_user.id))
    base = q.message.text_html if q.message else ""
    if accion == "ok":
        await q.answer("✅")
        sufijo = t("robada.confirmado", quien=quien)
    elif accion == "unban":
        res = await unfederate_ban(context.bot, db, uid, revoked_by=q.from_user.id, shadow=cfg.shadow)
        n = sum(1 for v in res.values() if v in ("ok", "shadow"))
        db.log_action(chat_id=chat_id, user_id=uid, username=None, message_id=None,
                      rule="cuenta_robada", action="noop", score=0, mode=cfg.mode,
                      payload={"decision": "desbaneada", "por": q.from_user.id})
        await q.answer("↩️")
        sufijo = t("robada.desbaneado", quien=quien, n=n)
    else:
        await q.answer(t("review.invalid_callback"))
        return
    try:
        await q.edit_message_text(base + sufijo, parse_mode="HTML", disable_web_page_preview=True)
    except TelegramError:
        pass


# --- Ajustes: comando /robadas (el panel tiene su submenú en `config_panel`) ---

def estado(db: DB, chat_id: int) -> str:
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    elegidos = elegidos_de(s)
    return t("robadas.estado", mencion=t(f"cfg.robadas.{mencion_de(s)}"),
             privado=t("on") if privado_de(s) else t("off"),
             elegidos=", ".join(f"<code>{i}</code>" for i in elegidos) or "—")


def cambiar_elegido(db: DB, chat_id: int, user_id: int, poner: bool) -> int:
    """Añade o quita a alguien de la lista de admins mencionados (respeta /sync)."""
    db.ensure_chat_settings(chat_id)
    ids = elegidos_de(db.get_chat_settings(chat_id))
    if poner and user_id not in ids:
        ids.append(user_id)
    elif not poner:
        ids = [i for i in ids if i != user_id]
    return settings_sync.apply_setting(db, chat_id, "robada_admins", ",".join(map(str, ids)) or None)


@permissions.bot_admin_only
async def cmd_robadas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/robadas [dueno|elegidos|todos] · [privado on|off] · [+|- @usuario o id]"""
    db: DB = context.bot_data["db"]
    msg = update.effective_message
    chat_id = update.effective_chat.id
    args = [a.lower() for a in (context.args or [])]
    if not args:
        await msg.reply_text(estado(db, chat_id), parse_mode="HTML")
        return
    if args[0] in MENCIONES:
        settings_sync.apply_setting(db, chat_id, "robada_mencion", args[0])
    elif args[0] == "privado" and len(args) > 1 and args[1] in ("on", "off"):
        settings_sync.apply_setting(db, chat_id, "robada_privado", int(args[1] == "on"))
    elif args[0] in ("+", "-") and len(args) > 1:
        crudo = args[1].lstrip("@")
        uid = int(crudo) if crudo.lstrip("-").isdigit() else db.resolve_username(crudo)
        if not uid:
            await msg.reply_text(t("robadas.no_encontrado"), parse_mode="HTML")
            return
        cambiar_elegido(db, chat_id, uid, args[0] == "+")
    else:
        await msg.reply_text(t("robadas.uso"), parse_mode="HTML")
        return
    await msg.reply_text(estado(db, chat_id), parse_mode="HTML")
