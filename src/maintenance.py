"""Jobs de mantenimiento periódicos para evitar crecimiento descontrolado de tablas.

Corre 1 vez al día (cleanup_nightly_job). Cada tabla tiene retención propia:
- reaction_events: 30 días
- gentle_warnings: 24h (el TTL real son 5 min, esto borra los huérfanos)
- pending_verifications verificadas: 7 días tras verified_at
- suppressions expiradas: borrar tras suppressed_until
- cas_cache entries con checked_at < 30 días
- moderation_log: mantener todo (auditoría)
- learning_samples: mantener todo (entrenamiento)

También aggressive cleanup post-ban si ban_recent_messages está activo.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from telegram.ext import ContextTypes

from .db import DB

log = logging.getLogger(__name__)


async def cleanup_nightly_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cleanup de tablas viejas. Corre cada 24h."""
    db: DB = context.bot_data["db"]
    stats = {}
    now = time.time()

    with db._cur() as c:
        # reaction_events > 30 días
        n = c.execute(
            "DELETE FROM reaction_events WHERE ts < ?", (now - 30 * 86400,),
        ).rowcount
        stats["reaction_events"] = n

        # gentle_warnings > 24h (el TTL es 5 min, esto barre huérfanos del bridge Telethon
        # que pudo no captar borrados muy antiguos)
        n = c.execute(
            "DELETE FROM gentle_warnings WHERE ts < ?", (now - 86400,),
        ).rowcount
        stats["gentle_warnings"] = n

        # pending_verifications verificadas hace >7 días
        n = c.execute(
            "DELETE FROM pending_verifications WHERE verified_at IS NOT NULL AND verified_at < ?",
            (now - 7 * 86400,),
        ).rowcount
        stats["pending_verifications_verified"] = n

        # pending_verifications no verificadas hace >30 días (improbable pero limpieza)
        n = c.execute(
            "DELETE FROM pending_verifications WHERE verified_at IS NULL AND joined_at < ?",
            (now - 30 * 86400,),
        ).rowcount
        stats["pending_verifications_stale"] = n

        # suppressions expiradas
        n = c.execute(
            "DELETE FROM suppressions WHERE suppressed_until < ?", (now,),
        ).rowcount
        stats["suppressions"] = n

        # cas_cache con TTL >30d (la lookup ya las ignora si TTL expira, pero limpiamos)
        n = c.execute(
            "DELETE FROM cas_cache WHERE checked_at < ?", (now - 30 * 86400,),
        ).rowcount
        stats["cas_cache"] = n

        # admin_reports resueltos >7 días → borrar
        n = c.execute(
            "DELETE FROM admin_reports WHERE resolved_at IS NOT NULL AND resolved_at < ?",
            (now - 7 * 86400,),
        ).rowcount
        stats["admin_reports_resolved"] = n

        # admin_reports sin resolver >30 días → borrar (los duplicados quedaban huérfanos)
        n = c.execute(
            "DELETE FROM admin_reports WHERE resolved_at IS NULL AND ts < ?",
            (now - 30 * 86400,),
        ).rowcount
        stats["admin_reports_stale"] = n

        # weekly_msg_log > 14 días (suficiente histórico para la semana actual)
        n = c.execute(
            "DELETE FROM weekly_msg_log WHERE ts < ?", (now - 14 * 86400,),
        ).rowcount
        stats["weekly_msg_log"] = n

        # VACUUM para reclamar espacio (solo si borramos >1000 filas)
        total = sum(stats.values())
        if total > 1000:
            c.execute("VACUUM")
            log.info("cleanup_nightly_job: VACUUM ejecutado tras borrar %d filas", total)

    if any(v > 0 for v in stats.values()):
        log.info("cleanup_nightly_job stats: %s", stats)
    else:
        log.debug("cleanup_nightly_job: nada que limpiar")

    # Reconciliación banned_users ↔ Telegram: si el bot ya no tiene a un user
    # como kicked en NINGÚN chat federado, marcar revoked en BD para evitar
    # que dispare federation_known_ban al reentrar. Cubre desincronización
    # por unbans manuales en Telegram que el bot no ve.
    await _reconcile_banned_users(context, db)


async def _reconcile_banned_users(context, db) -> None:
    """Marca como revoked en banned_users a los users que ya no están kicked
    en ningún chat federado del bot. Best-effort, no rompe el job nightly."""
    from telegram.constants import ChatMemberStatus
    cfg = context.bot_data.get("cfg")
    if cfg is None:
        return
    # Lista de chats federados (admin_chats)
    try:
        chats = db.admin_chats() if hasattr(db, "admin_chats") else []
    except Exception as exc:  # noqa: BLE001
        log.warning("reconcile_banned_users: admin_chats() falló: %s", exc)
        return
    if not chats:
        log.debug("reconcile_banned_users: sin chats federados")
        return
    # Users pendientes de revocar (banned sin revoke, registrados en últimos 30 días
    # para no spammear getChatMember sobre bans muy viejos)
    import time as _t
    cutoff = _t.time() - 30 * 86400
    with db._cur() as c:
        rows = c.execute(
            "SELECT user_id FROM banned_users "
            "WHERE revoked_at IS NULL AND banned_at > ?",
            (cutoff,),
        ).fetchall()
    pending = [r["user_id"] for r in rows]
    if not pending:
        log.debug("reconcile_banned_users: nada que reconciliar")
        return
    log.info("reconcile_banned_users: %d users a verificar", len(pending))
    revoked = 0
    for uid in pending:
        kicked_anywhere = False
        for cid in chats:
            try:
                member = await context.bot.get_chat_member(chat_id=cid, user_id=uid)
                if member.status == ChatMemberStatus.BANNED:
                    kicked_anywhere = True
                    break
            except Exception as exc:  # noqa: BLE001
                log.debug("reconcile get_chat_member fallo chat=%s uid=%s: %s",
                          cid, uid, exc)
        if not kicked_anywhere:
            with db._cur() as c:
                c.execute(
                    "UPDATE banned_users SET revoked_at=?, revoked_by=? "
                    "WHERE user_id=? AND revoked_at IS NULL",
                    (_t.time(), 0, uid),  # revoked_by=0 = sistema
                )
            revoked += 1
    if revoked > 0:
        log.info("reconcile_banned_users: %d users revocados (ya no kicked en Telegram)", revoked)


async def aggressive_post_ban_cleanup(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    max_messages: int = 30,
    since_seconds: int = 7 * 86400,
) -> int:
    """Tras un ban, intenta borrar los mensajes recientes del user en ese chat.

    Solo borra mensajes loggeados en moderation_log que estén dentro de la ventana
    de tiempo. NO usa Telethon (que tendría más cobertura) — más conservador.
    Devuelve count de mensajes borrados.
    """
    db: DB = context.bot_data["db"]
    cutoff = time.time() - since_seconds
    with db._cur() as c:
        rows = c.execute(
            """
            SELECT DISTINCT message_id FROM moderation_log
            WHERE chat_id=? AND user_id=? AND message_id IS NOT NULL AND ts >= ?
            ORDER BY ts DESC LIMIT ?
            """,
            (chat_id, user_id, cutoff, max_messages),
        ).fetchall()
    deleted = 0
    for r in rows:
        msg_id = r["message_id"]
        try:
            ok = await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            if ok:
                deleted += 1
        except Exception:
            pass
    if deleted:
        log.info("aggressive_post_ban_cleanup: %d msgs borrados chat=%s user=%s", deleted, chat_id, user_id)
    return deleted
