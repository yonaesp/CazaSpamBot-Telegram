"""Sistema de permisos del bot.

Tres niveles:
- **bot_admin** (ADMIN_USER_ID): único que puede MODIFICAR cosas (ban, setwelcome, etc.)
- **chat_admin**: admins de cualquiera de los grupos donde el bot opera.
  Pueden VER información (stats, recent, samples, etc.) pero NO modificar.
- **user**: usuarios normales. Solo `@admin` (público) y mensaje de bienvenida.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import ContextTypes

log = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 min cache de admin status


async def is_chat_admin_any(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """True si user_id es admin de CUALQUIER chat donde el bot opera."""
    if not user_id:
        return False
    from .db import DB
    db: DB = context.bot_data["db"]
    cache = context.bot_data.setdefault("_admin_any_cache", {})
    now = time.time()
    cached = cache.get(user_id)
    if cached and cached[1] > now:
        return cached[0]
    for row in db.all_chats():
        if not row["am_admin"]:
            continue
        try:
            member = await context.bot.get_chat_member(chat_id=row["chat_id"], user_id=user_id)
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                cache[user_id] = (True, now + _CACHE_TTL)
                return True
        except TelegramError:
            pass
    cache[user_id] = (False, now + _CACHE_TTL)
    return False


def is_bot_admin(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """True si user_id es el ADMIN_USER_ID configurado en .env (ADMIN_USER_ID)."""
    from .config import Config
    cfg: Config = context.bot_data["cfg"]
    return user_id == cfg.admin_user_id


# --- Decorators ---

def bot_admin_only(func):
    """Solo el bot admin (ADMIN_USER_ID) puede ejecutar. Otros se ignoran silenciosamente."""
    async def wrapper(update, context):
        u = update.effective_user
        if not u or not is_bot_admin(context, u.id):
            return
        return await func(update, context)
    return wrapper


def chat_admin_or_bot_admin(func):
    """Bot admin (ADMIN_USER_ID) O admin de cualquier chat moderado.

    Los admins de los grupos pueden VER información pero los comandos que
    MODIFICAN deben usar bot_admin_only.
    """
    async def wrapper(update, context):
        u = update.effective_user
        if not u:
            return
        if is_bot_admin(context, u.id):
            return await func(update, context)
        if await is_chat_admin_any(context, u.id):
            return await func(update, context)
        # User normal → silencio
    return wrapper
