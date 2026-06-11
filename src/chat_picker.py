"""Helper para que comandos de consulta funcionen en DM con selector de grupo.

Patrón:
1. User envía /comando en DM con el bot
2. Bot detecta DM, no hay chat target → muestra inline keyboard con los grupos
3. User pulsa botón → callback "pick:<comando>:<chat_id>"
4. Handler resuelve y ejecuta el comando como si estuviera en ese grupo
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .db import DB

log = logging.getLogger(__name__)

PICK_PREFIX = "pick"


def is_dm(update: Update) -> bool:
    return update.effective_chat is not None and update.effective_chat.type == "private"


async def show_chat_picker(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    command_name: str,
    args_suffix: str = "",
) -> None:
    """Muestra inline keyboard con los chats donde el bot es admin."""
    db: DB = context.bot_data["db"]
    chats = db.all_chats()
    admin_chats = [c for c in chats if c["am_admin"]]
    if not admin_chats:
        await update.effective_message.reply_text("Sin chats registrados todavía.")
        return
    rows = []
    for c in admin_chats:
        title = (c["title"] or str(c["chat_id"]))[:50]
        cb = f"{PICK_PREFIX}:{command_name}:{c['chat_id']}"
        if args_suffix:
            cb += f":{args_suffix}"
        rows.append([InlineKeyboardButton(title, callback_data=cb)])
    await update.effective_message.reply_text(
        f"🔍 ¿De qué grupo quieres ver <code>/{command_name}</code>?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )


# Registry de handlers por command_name. Cada función recibe (update, context, chat_id, args)
PickerHandler = Callable[[Update, ContextTypes.DEFAULT_TYPE, int, str], Awaitable[None]]
_HANDLERS: dict[str, PickerHandler] = {}


def register(command_name: str, handler: PickerHandler) -> None:
    _HANDLERS[command_name] = handler


async def on_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa el click del picker."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith(f"{PICK_PREFIX}:"):
        return
    from .config import Config
    cfg: Config = context.bot_data["cfg"]
    if query.from_user.id != cfg.admin_user_id:
        await query.answer("Solo admin.", show_alert=True)
        return
    parts = query.data.split(":", 3)
    if len(parts) < 3:
        await query.answer("Botón inválido.")
        return
    command_name = parts[1]
    try:
        chat_id = int(parts[2])
    except ValueError:
        await query.answer("Chat_id inválido.")
        return
    args = parts[3] if len(parts) > 3 else ""
    handler = _HANDLERS.get(command_name)
    if not handler:
        await query.answer(f"Sin handler para {command_name}")
        return
    await query.answer()
    try:
        await handler(update, context, chat_id, args)
    except Exception as exc:
        log.warning("picker handler %s exc: %s", command_name, exc)
        await query.edit_message_text(f"Error: {exc}")
