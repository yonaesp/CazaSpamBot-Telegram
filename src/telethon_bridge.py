"""Listener Telethon para eventos que Bot API no entrega.

Específicamente: cuando un usuario borra su propio mensaje, Telegram NO manda
update al bot. Telethon (cliente MTProto) sí recibe `UpdateDeleteMessages` /
`UpdateDeleteChannelMessages`. Este módulo escucha esos events y borra en
cascada los avisos del bot que respondieron a esos mensajes.
"""
from __future__ import annotations

import asyncio
import html as _h
import logging
import os
import time as _t
from typing import Any

from telegram import Bot
from telegram.error import TelegramError

from .db import DB

log = logging.getLogger(__name__)


def attach(client, bot: Bot, db: DB) -> None:
    """Registra el handler MessageDeleted en el cliente Telethon."""
    try:
        from telethon import events
    except ImportError:
        log.warning("telethon no disponible para attach()")
        return

    @client.on(events.MessageDeleted)
    async def _on_deleted(event: Any) -> None:
        try:
            chat_id = event.chat_id
            if not chat_id:
                return
            # Telethon usa chat_id sin -100 prefix para canales/supergrupos.
            # Para grupos PTB usamos -100xxxx. Compensamos.
            if chat_id > 0:
                full_chat_id = int(f"-100{chat_id}")
            else:
                full_chat_id = chat_id
            from . import admin_report as ar_mod
            for msg_id in event.deleted_ids:
                # 1) Cascade gentle_warnings (bot avisó a user, user borra → borrar aviso)
                bot_msg = db.pop_gentle_warning_by_user_msg(full_chat_id, msg_id)
                if bot_msg:
                    try:
                        await bot.delete_message(chat_id=full_chat_id, message_id=bot_msg)
                        log.info(
                            "gentle_warning cascada: borrado bot_msg=%s tras delete user_msg=%s en chat=%s",
                            bot_msg, msg_id, full_chat_id,
                        )
                    except TelegramError as exc:
                        log.debug("delete bot_msg fallo: %s", exc)
                # 2) Cascade admin_reports (admin borra msg reportado → borrar @admin + thanks)
                try:
                    await ar_mod.on_reported_message_deleted(bot, db, full_chat_id, msg_id)
                except Exception as exc:
                    log.warning("admin_report cascade exc: %s", exc)
                # 3) Notif manual delete: si el bot NO borró este msg recientemente
                # y tenemos su contenido en seen_users, avisar al admin.
                try:
                    await _notify_manual_delete(client, bot, db, full_chat_id, msg_id)
                except Exception as exc:
                    log.warning("notify_manual_delete exc msg=%s: %s", msg_id, exc)
        except Exception as exc:
            log.warning("on_deleted exc: %s", exc)


async def _notify_manual_delete(client, bot: Bot, db: DB, chat_id: int, msg_id: int) -> None:
    """Si un msg fue borrado y el bot NO lo borró (no aparece en moderation_log
    como acción reciente), notifica al admin con el contenido guardado en
    seen_users y, si Telethon puede, quién lo borró según admin_log del chat.
    """
    # 1) Saltar si el bot ya actuó sobre ese msg en los últimos 60s
    now = _t.time()
    with db._cur() as c:
        recent = c.execute(
            "SELECT action FROM moderation_log "
            "WHERE chat_id=? AND message_id=? AND ts > ? "
            "AND action IN ('ban','kick','mute','delete') "
            "ORDER BY ts DESC LIMIT 1",
            (chat_id, msg_id, now - 60),
        ).fetchone()
    if recent:
        log.debug("manual_delete skip msg=%s: bot ya hizo %s", msg_id, recent["action"])
        return

    # 2) Recuperar contenido y autor desde seen_users.last_msg_*
    with db._cur() as c:
        seen = c.execute(
            "SELECT user_id, first_name, last_msg_text FROM seen_users "
            "WHERE chat_id=? AND last_msg_id=?",
            (chat_id, msg_id),
        ).fetchone()
    if not seen or not seen["last_msg_text"]:
        # Sin contenido guardado, no merece la pena notificar (sería ruido)
        return
    text = seen["last_msg_text"] or "(sin texto)"
    author_id = seen["user_id"]
    author_name = seen["first_name"] or "?"

    # 3) Identificar al admin que borró via admin_log de Telethon
    # Bots cuyos borrados NO son moderación y NO merecen aviso (ruido):
    #   - el propio bot (su id se obtiene en runtime, no se hardcodea),
    #   - los bots de automatización listados en SKIP_DELETE_NOTIF_BOTS (CSV de
    #     user_ids en .env). Ej: un bot que reemplaza enlaces de Amazon por
    #     referidos borra y repone el mensaje; es su función normal, no spam.
    own_id = getattr(bot, "id", None)
    skip_extra = {
        int(x) for x in os.getenv("SKIP_DELETE_NOTIF_BOTS", "").replace(" ", "").split(",")
        if x.strip().lstrip("-").isdigit()
    }
    SKIP_DELETE_NOTIF_BOTS = ({own_id} if own_id else set()) | skip_extra
    actor_info = "?"
    actor_id_found = None
    try:
        entity = await client.get_entity(chat_id)
        async for entry in client.iter_admin_log(entity, limit=20, delete=True):
            action = getattr(entry, "action", None)
            deleted_msg = getattr(action, "message", None) if action else None
            if deleted_msg is not None and getattr(deleted_msg, "id", None) == msg_id:
                actor = getattr(entry, "user", None)
                if actor is None and getattr(entry, "user_id", None):
                    actor = await client.get_entity(entry.user_id)
                if actor is not None:
                    name = getattr(actor, "first_name", None) or "?"
                    uname = getattr(actor, "username", None)
                    aid = getattr(actor, "id", "?")
                    actor_id_found = aid
                    tag = f"@{uname}" if uname else name
                    actor_info = f"{_h.escape(tag)} (<code>{aid}</code>)"
                break
    except Exception as exc:  # noqa: BLE001
        log.debug("manual_delete admin_log lookup fallo chat=%s: %s", chat_id, exc)

    # Si el borrado lo hizo el PROPIO bot o un bot de automatización conocido
    # (referidos Amazon, etc.), NO notificar: no es moderación, es ruido.
    if actor_id_found in SKIP_DELETE_NOTIF_BOTS:
        log.debug("manual_delete skip: borrado por bot conocido %s msg=%s", actor_id_found, msg_id)
        return

    # Si NO se pudo atribuir el borrado a un admin (actor "?"), casi siempre es el
    # propio usuario borrando su mensaje (self-delete); admin_log solo registra
    # borrados de admins. Para algunos es ruido, para otros es info útil. Se
    # controla con NOTIFY_SELF_DELETES (default false → no avisar de self-deletes).
    notify_self_deletes = os.getenv("NOTIFY_SELF_DELETES", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if actor_id_found is None and not notify_self_deletes:
        log.debug("manual_delete skip: borrador desconocido (self-delete) y NOTIFY_SELF_DELETES=false msg=%s", msg_id)
        return

    # 4) Título del chat
    chat_title = str(chat_id)
    with db._cur() as c:
        row = c.execute("SELECT title FROM bot_chats WHERE chat_id=?", (chat_id,)).fetchone()
        if row and row["title"]:
            chat_title = row["title"]

    # 5) Notif al admin via CazaSpamBot (no Casa_Yona, mismo flujo que admin_report)
    admin_id_env = os.getenv("ADMIN_USER_ID", "0")
    try:
        admin_id = int(admin_id_env)
    except ValueError:
        admin_id = 0
    if admin_id <= 0:
        return
    # Perfil del autor clicable (DM privado al admin, sin riesgo de visibilidad)
    author_link = (
        f'<a href="tg://user?id={author_id}">{_h.escape(author_name)}</a>'
        if author_id else _h.escape(author_name)
    )
    # ¿Sigue el autor baneado/en el grupo? (informa de su estado actual)
    estado = ""
    if author_id:
        try:
            row = None
            with db._cur() as c:
                row = c.execute(
                    "SELECT 1 FROM banned_users WHERE user_id=? AND revoked_at IS NULL",
                    (author_id,),
                ).fetchone()
            estado = "\n⚖️ Estado: 🔨 <b>baneado</b> en la federación" if row else "\n⚖️ Estado: sigue en el grupo (solo se borró el msg)"
        except Exception:  # noqa: BLE001
            pass
    notif = (
        f"🗑️ <b>Mensaje borrado manualmente</b>\n"
        f"📍 Chat: {_h.escape(chat_title)}\n"
        f"👮 Borrado por: {actor_info}\n"
        f"👤 Autor del msg: {author_link} (<code>{author_id or '?'}</code>)"
        f"{estado}\n"
        f"🆔 msg_id: <code>{msg_id}</code>\n\n"
        f"<b>Contenido:</b>\n<pre>{_h.escape(text[:600])}</pre>"
    )
    try:
        await bot.send_message(
            chat_id=admin_id, text=notif, parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except TelegramError as exc:
        log.debug("manual_delete notif send fallo: %s", exc)
