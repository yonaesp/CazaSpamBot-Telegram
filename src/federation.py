"""Federación cross-group: replica bans a todos los chats donde el bot es admin."""
from __future__ import annotations

import asyncio
import logging

from telegram import Bot
from telegram.error import TelegramError

from .db import DB

log = logging.getLogger(__name__)


async def federate_ban(
    bot: Bot,
    db: DB,
    user_id: int,
    reason: str,
    rule: str,
    triggered_in_chat: int,
    shadow: bool,
) -> dict[int, str]:
    """Bania al usuario en todos los chats donde el bot es admin.

    Devuelve {chat_id: "ok" | "shadow" | "error: ..."}.

    Nota: la persistencia en `banned_users` se hace al FINAL del loop, solo si
    al menos un chat se baneó correctamente. Evita registros huérfanos cuando
    todos los bans fallan (p.ej. el user ya no existe, bot perdió permisos).
    """
    results: dict[int, str] = {}
    chats = db.admin_chats()
    if not chats:
        chats = [triggered_in_chat]

    async def _ban_one(chat_id: int) -> tuple[int, str]:
        if shadow:
            return chat_id, "shadow"
        try:
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            return chat_id, "ok"
        except TelegramError as exc:
            return chat_id, f"error: {exc.message}"

    coros = [_ban_one(cid) for cid in chats]
    for coro in asyncio.as_completed(coros):
        cid, status = await coro
        results[cid] = status
        if status.startswith("error"):
            log.warning("Federación ban fallo en chat %s: %s", cid, status)

    # Registrar el ban solo si al menos un chat lo aplicó (o si es shadow)
    any_applied = any(v in ("ok", "shadow") for v in results.values())
    if any_applied:
        db.add_ban(
            user_id=user_id, reason=reason, rule=rule,
            banned_in_chat=triggered_in_chat, federated=True,
        )
    else:
        log.warning(
            "federate_ban: ningún chat aplicó ban user=%s (todos fallaron); NO se registra",
            user_id,
        )
    return results


async def unfederate_ban(
    bot: Bot,
    db: DB,
    user_id: int,
    revoked_by: int,
    shadow: bool,
) -> dict[int, str]:
    db.revoke_ban(user_id, revoked_by)
    results: dict[int, str] = {}
    for chat_id in db.admin_chats():
        if shadow:
            results[chat_id] = "shadow"
            continue
        try:
            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
            results[chat_id] = "ok"
        except TelegramError as exc:
            results[chat_id] = f"error: {exc.message}"
            log.warning("Unban fallo en chat %s: %s", chat_id, exc.message)
    return results
