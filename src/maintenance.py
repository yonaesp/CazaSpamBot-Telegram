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

import html as _h
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import notify_prefs
from .db import DB
from .i18n import t

log = logging.getLogger(__name__)


# Copias de seguridad de la BD: cuántas se conservan (una por noche).
BACKUP_KEEP = 7
BACKUP_DIRNAME = "backups"


def backup_database(db_path: str | Path, keep: int = BACKUP_KEEP) -> Path | None:
    """Copia CONSISTENTE de la BD en `<data>/backups/antispam-YYYYMMDD.db`.

    Usa `VACUUM INTO`, que escribe una base íntegra aunque el bot esté escribiendo
    a la vez. Copiar el fichero a pelo NO vale: en modo WAL el `.db` puede llevar
    días sin recibir un checkpoint y la copia sale vieja (medido: 5 baneos y 20
    registros de auditoría de menos), y copiarlo mientras se escribe puede además
    dar una foto inconsistente.

    Rota dejando las `keep` más recientes. Devuelve la ruta creada, o None si falla:
    esto es mantenimiento, y nunca debe abortar el resto del job.
    """
    origen = Path(db_path)
    # Sin esta guarda, `sqlite3.connect` CREARÍA la base vacía y acabaríamos
    # guardando una copia de cero filas que además rotaría fuera a las buenas.
    if not origen.is_file():
        log.warning("backup: la base %s no existe, no se copia nada", origen)
        return None
    destino_dir = origen.parent / BACKUP_DIRNAME
    fecha = datetime.now(timezone.utc).strftime("%Y%m%d")
    destino = destino_dir / f"antispam-{fecha}.db"
    try:
        destino_dir.mkdir(parents=True, exist_ok=True)
        # VACUUM INTO falla si el destino ya existe: al reejecutar el mismo día se
        # rehace la copia (queda la más reciente del día, que es lo que interesa).
        destino.unlink(missing_ok=True)
        # Conexión propia y de solo lectura lógica: no interfiere con la del bot.
        con = sqlite3.connect(str(origen), timeout=30)
        try:
            con.execute("VACUUM INTO ?", (str(destino),))
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001 — sin copia se sigue; se avisa y se reintenta mañana
        log.warning("backup: no se pudo crear la copia (%s); se reintenta mañana", exc)
        return None

    # Rotación: deja las `keep` más recientes por nombre (el nombre lleva la fecha).
    try:
        copias = sorted(destino_dir.glob("antispam-*.db"))
        for vieja in copias[:-keep] if keep > 0 else []:
            vieja.unlink(missing_ok=True)
            log.debug("backup: rotada %s", vieja.name)
    except Exception as exc:  # noqa: BLE001 — que falle la rotación no invalida la copia
        log.warning("backup: rotación fallida (%s)", exc)

    log.info("backup: copia consistente en %s (%.1f KB)",
             destino.name, destino.stat().st_size / 1024)
    return destino


async def cleanup_nightly_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cleanup de tablas viejas. Corre cada 24h."""
    db: DB = context.bot_data["db"]
    stats = {}
    now = time.time()

    # Copia de seguridad ANTES de limpiar y compactar: si algo saliera mal en el
    # borrado o en el VACUUM, la copia de la noche refleja el estado previo.
    try:
        backup_database(db.path)
    except Exception as exc:  # noqa: BLE001 — jamás debe abortar el mantenimiento
        log.warning("backup: error inesperado (%s)", exc)

    with db._cur() as c:
        # reaction_events > 30 días
        n = c.execute(
            "DELETE FROM reaction_events WHERE ts < ?", (now - 30 * 86400,),
        ).rowcount
        stats["reaction_events"] = n

        # admin_ban_events > 7 días (solo se usan en ventanas de pocas horas)
        n = c.execute(
            "DELETE FROM admin_ban_events WHERE ts < ?", (now - 7 * 86400,),
        ).rowcount
        stats["admin_ban_events"] = n

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

        # weekly_msg_log > 31 días. Eran 14 (bastaba para el top semanal), pero
        # /scanuser informa de la actividad del ÚLTIMO MES y con 14 días habría que
        # mentir o dar otra ventana. El coste es ridículo: ~180 filas en 14 días.
        n = c.execute(
            "DELETE FROM weekly_msg_log WHERE ts < ?", (now - 31 * 86400,),
        ).rowcount
        stats["weekly_msg_log"] = n

        # VACUUM para reclamar espacio (solo si borramos >1000 filas)
        total = sum(stats.values())
        if total > 1000:
            # VACUUM pide lock exclusivo de toda la BD. Si otro proceso (p.ej. un
            # script de análisis) tiene una lectura abierta, falla con "database is
            # locked". Sin proteger, esa excepción abortaba cleanup_nightly_job y
            # _reconcile_banned_users NO llegaba a correr esa noche.
            try:
                c.execute("VACUUM")
                log.info("cleanup_nightly_job: VACUUM ejecutado tras borrar %d filas", total)
            except Exception as exc:  # noqa: BLE001
                log.warning("cleanup_nightly_job: VACUUM omitido (%s); se reintenta mañana", exc)

    if any(v > 0 for v in stats.values()):
        log.info("cleanup_nightly_job stats: %s", stats)
    else:
        log.debug("cleanup_nightly_job: nada que limpiar")

    # Reconciliación banned_users ↔ Telegram: si el bot ya no tiene a un user
    # como kicked en NINGÚN chat federado, marcar revoked en BD para evitar
    # que dispare federation_known_ban al reentrar. Cubre desincronización
    # por unbans manuales en Telegram que el bot no ve.
    await _reconcile_banned_users(context, db)

    # Aviso (una sola vez por pareja chat+bot) de otro bot admin en el grupo.
    try:
        await notify_bot_overlap(context)
    except Exception as exc:  # noqa: BLE001 — es informativo: nunca aborta el mantenimiento
        log.warning("bot_overlap: error inesperado (%s)", exc)


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
    sin_respuesta = 0
    for uid in pending:
        kicked_anywhere = False
        lookup_ok = False  # ¿respondió AL MENOS una consulta?
        for cid in chats:
            try:
                member = await context.bot.get_chat_member(chat_id=cid, user_id=uid)
                lookup_ok = True
                if member.status == ChatMemberStatus.BANNED:
                    kicked_anywhere = True
                    break
            except Exception as exc:  # noqa: BLE001
                log.debug("reconcile get_chat_member fallo chat=%s uid=%s: %s",
                          cid, uid, exc)
        # Solo revocamos ante un "ya no está baneado" CONFIRMADO. Si ninguna consulta
        # respondió (red caída, 5xx de Telegram, flood-wait, o el bot perdió admin),
        # "fallo" es indistinguible de "no baneado": revocar ahí borraría un ban real
        # y dejaría de re-banear a ese spammer al reentrar (is_banned filtra por
        # revoked_at IS NULL). Ante la duda, no se toca.
        if not lookup_ok:
            sin_respuesta += 1
            continue
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
    if sin_respuesta > 0:
        log.warning("reconcile_banned_users: %d users sin respuesta de Telegram en ningún "
                    "chat; NO se revocan (se reintenta en la próxima pasada)", sin_respuesta)


# ===== Aviso: otro bot admin en el grupo (posible solape de funciones) =====

def _overlap_key(chat_id: int, bot_id: int) -> str:
    """Clave de la marca «ya avisé de este bot en este chat».

    Vive en `bot_prefs` (get_pref/set_pref) porque lo que se guarda es exactamente
    un booleano «ya avisado»: no hace falta tabla nueva ni migración, y son cuatro
    filas contadas (una por pareja). El prefijo es distinto de `notify_` para que
    nunca se cruce con las preferencias de /alertas.
    """
    return f"botoverlap_{chat_id}_{bot_id}"


def _overlap_keyboard(chat_id: int):
    """Botones del aviso: abrir los ajustes de ESE grupo, y silenciar el aviso."""
    from .config_panel import PREFIX as CFG  # local: mantiene maintenance ligero
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("maint.bot_overlap.b.config"),
                              callback_data=f"{CFG}:open:{chat_id}")],
        [notify_prefs.mute_button("bot_overlap")],
    ])


async def notify_bot_overlap(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Avisa al admin de que en un grupo moderado hay OTRO bot con permisos de admin.

    No se puede saber qué hace ese bot (no hay forma de introspeccionarlo), así que el
    aviso dice que PUEDE solaparse, no que lo haga. Se manda **una sola vez por pareja
    chat+bot**: repetirlo cada noche solo consigue que el admin lo silencie por hartazgo.

    Devuelve cuántos avisos se enviaron. Best-effort: cualquier fallo se registra y se
    sigue con el resto de grupos.
    """
    db: DB = context.bot_data["db"]
    cfg = context.bot_data.get("cfg")
    if cfg is None:
        return 0
    if not notify_prefs.effective(db, "bot_overlap", cfg):
        return 0
    # Mismo destino que el resto de avisos: el chat de notificaciones si está
    # configurado, y si no el DM del admin.
    destino = getattr(cfg, "admin_notify_chat_id", 0) or getattr(cfg, "admin_user_id", 0)
    if not destino:
        return 0
    try:
        chats = [c for c in db.all_chats() if c["am_admin"]]
    except Exception as exc:  # noqa: BLE001
        log.warning("bot_overlap: no se pudieron listar los grupos (%s)", exc)
        return 0
    yo = getattr(context.bot, "id", None)
    enviados = 0
    for c in chats:
        cid = c["chat_id"]
        try:
            admins = await context.bot.get_chat_administrators(chat_id=cid)
        except Exception as exc:  # noqa: BLE001 — un chat que falla no frena a los demás
            log.debug("bot_overlap: get_chat_administrators falló chat=%s: %s", cid, exc)
            continue
        for miembro in admins or []:
            otro = getattr(miembro, "user", None)
            if otro is None or not getattr(otro, "is_bot", False):
                continue
            if yo is not None and otro.id == yo:
                continue  # yo mismo no cuento
            clave = _overlap_key(cid, otro.id)
            if db.get_pref(clave):
                continue  # ya avisado de esta pareja
            texto = t(
                "maint.bot_overlap",
                chat=_h.escape(c["title"] or str(cid)),
                chat_id=cid,
                bot=_h.escape(otro.first_name or otro.username or str(otro.id)),
                bot_user=(f" (@{_h.escape(otro.username)})" if otro.username else ""),
            )
            try:
                await context.bot.send_message(
                    chat_id=destino, text=texto, parse_mode="HTML",
                    reply_markup=_overlap_keyboard(cid),
                )
            except TelegramError as exc:
                # Sin marca: se reintenta en la siguiente pasada. Marcar aquí dejaría
                # al admin sin enterarse nunca de ese solape.
                log.debug("bot_overlap: aviso no enviado chat=%s bot=%s: %s", cid, otro.id, exc)
                continue
            db.set_pref(clave, True)
            enviados += 1
            log.info("bot_overlap: avisado de %s (%s) admin en chat=%s",
                     otro.username or otro.first_name, otro.id, cid)
    return enviados


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
