"""Federación cross-group: replica bans a todos los chats donde el bot es admin."""
from __future__ import annotations

import asyncio
import time
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

    # Y se retiran sus mensajes. Banear en un supergrupo NO los borra: caso real
    # (26-sep-2026, Windows 11), una cuenta mandó cuatro reenvíos de publicidad
    # porno, el admin pulsó «Spam» a las 08:57 y a las 11:00 seguían tres en el
    # grupo, porque solo se borraba el mensaje revisado. La función que debía
    # hacerlo (`aggressive_post_ban_cleanup`, ya retirada) no la llamaba nadie y
    # además solo miraba `moderation_log`, donde el cuarto ni aparecía.
    # Solo Bot API y solo en los chats donde el ban se aplicó de verdad.
    if not shadow:
        await _retirar_mensajes(bot, db, user_id,
                                [cid for cid, v in results.items() if v == "ok"])

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


# Ventana de mensajes a retirar tras un ban. `mensajes_recientes` guarda 7 días.
LIMPIEZA_VENTANA_S = 7 * 86400


async def _retirar_mensajes(bot: Bot, db: DB, user_id: int, chats: list[int]) -> int:
    """Borra lo que el baneado escribió en esos chats. Nunca lanza."""
    try:
        por_chat = db.mensajes_para_limpiar(user_id, time.time() - LIMPIEZA_VENTANA_S)
    except Exception as exc:  # noqa: BLE001
        log.warning("limpieza post-ban: sin lista de mensajes user=%s: %s", user_id, exc)
        return 0
    total = 0
    for cid in chats:
        ids = list(por_chat.get(cid) or [])
        # Y los avisos del bot ligados a esa persona («un admin lo revisará»,
        # avisos suaves): con sus mensajes fuera quedarían respondiendo a nada.
        try:
            ids += db.pop_avisos_de_usuario(cid, user_id)
        except Exception as exc:  # noqa: BLE001
            log.debug("limpieza post-ban: avisos ilegibles chat=%s: %s", cid, exc)
        for i in range(0, len(ids), 100):          # deleteMessages admite 100 por llamada
            trozo = ids[i:i + 100]
            try:
                await bot.delete_messages(chat_id=cid, message_ids=trozo)
                total += len(trozo)
            except TelegramError as exc:
                # Ya borrados o demasiado viejos: no es un fallo que importe.
                log.debug("limpieza post-ban chat=%s: %s", cid, exc.message)
            except Exception as exc:  # noqa: BLE001 — la limpieza jamás tumba un ban
                log.warning("limpieza post-ban chat=%s: %s", cid, exc, exc_info=True)
    if total:
        log.info("limpieza post-ban user=%s: %d mensajes retirados en %d chats",
                 user_id, total, len([c for c in chats if por_chat.get(c)]))
    return total


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
