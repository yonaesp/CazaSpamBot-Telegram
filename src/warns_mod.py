"""Sistema de warnings estilo Rose.

Comandos:
  /warn (reply)       — añade warn; al alcanzar límite, ejecuta warns_action
  /warns (reply)      — lista warns activos del user
  /rmwarn (reply)     — quita el último warn
  /resetwarns (reply) — borra todos los warns del user
  /warnlimit [N]      — getter/setter del límite del chat
  /warnaction [v]     — getter/setter de la acción (kick|ban|mute)
"""
from __future__ import annotations

import asyncio
import html
import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from .config import Config
from .db import DB
from .federation import federate_ban

log = logging.getLogger(__name__)


def _admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        cfg: Config = context.bot_data["cfg"]
        u = update.effective_user
        if not u or u.id != cfg.admin_user_id:
            return
        return await func(update, context)
    return wrapper


def _get_target(update: Update) -> tuple[int | None, str | None]:
    msg = update.effective_message
    if msg and msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        return u.id, u.username or u.first_name
    return None, None


@_admin_only
async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Warna a un usuario. Acepta:
    - /warn [razón]  responding a un mensaje
    - /warn @username [razón]
    - /warn <user_id> [razón]

    Si hay reply, borra el msg warneado + el comando del admin.
    Si no hay reply, solo borra el comando admin y publica el warn.
    Si el msg warneado tenía un reporte @admin → marca action_taken='warn'.
    """
    from telegram.constants import ChatMemberStatus
    from telegram.error import TelegramError

    msg = update.effective_message
    db: DB = context.bot_data["db"]
    cfg: Config = context.bot_data["cfg"]

    # Resolver target: reply || arg @username || arg user_id
    target_id: int | None = None
    target_user = None
    target_msg = msg.reply_to_message
    reason_parts = list(context.args) if context.args else []

    if target_msg and target_msg.from_user:
        target_user = target_msg.from_user
        target_id = target_user.id
    elif reason_parts:
        first = reason_parts[0]
        if first.lstrip("-").isdigit():
            target_id = int(first)
            reason_parts = reason_parts[1:]
        elif first.startswith("@"):
            uname = first[1:]
            target_id = db.resolve_username(uname)
            if target_id is None:
                # Fallback: getChat via API (solo si es @username público)
                try:
                    chat_obj = await context.bot.get_chat(first)
                    target_id = chat_obj.id
                except Exception as exc:  # noqa: BLE001
                    log.debug("warn get_chat(@%s) fallo: %s", uname, exc)
            reason_parts = reason_parts[1:]
        if target_id:
            try:
                member = await context.bot.get_chat_member(chat_id=msg.chat_id, user_id=target_id)
                target_user = member.user
            except Exception as exc:  # noqa: BLE001
                log.debug("warn get_chat_member chat=%s user=%s fallo: %s", msg.chat_id, target_id, exc)

    if not target_id:
        await msg.reply_text(
            "Uso: <code>/warn [razón]</code> respondiendo a un mensaje, "
            "o <code>/warn @username [razón]</code>, o <code>/warn user_id [razón]</code>.",
            parse_mode="HTML",
        )
        return

    # GUARD: nunca warnear a un admin del chat
    try:
        member = await context.bot.get_chat_member(chat_id=msg.chat_id, user_id=target_id)
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await msg.reply_text(
                "⚠️ No puedo warnear a un admin del chat. Si necesitas hacerlo, hazlo manualmente.",
                parse_mode="HTML",
            )
            return
    except Exception as exc:  # noqa: BLE001
        log.debug("warn admin-guard get_chat_member fallo chat=%s user=%s: %s",
                  msg.chat_id, target_id, exc)

    reason = " ".join(reason_parts) if reason_parts else None
    db.ensure_chat_settings(msg.chat_id)
    settings = db.get_chat_settings(msg.chat_id)

    n = db.add_warn(target_id, msg.chat_id, update.effective_user.id, reason)
    limit = settings["warns_limit"] or 3
    action = settings["warns_action"] or "ban"

    # Marcar admin_report si existía → cascade usará template warn-específico
    if target_msg:
        db.mark_admin_report_action(msg.chat_id, target_msg.message_id, "warn")

    # Mención clicable al user warneado
    if target_user and target_user.username:
        mention = f"@{target_user.username}"
    elif target_user:
        display = html.escape(target_user.first_name or str(target_user.id))
        mention = f'<a href="tg://user?id={target_user.id}">{display}</a>'
    else:
        mention = f'<a href="tg://user?id={target_id}">user</a>'

    # 1) Borrar el comando /warn del admin
    try:
        await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
    except TelegramError:
        pass
    # 2) Borrar el mensaje warneado SOLO si había reply (es el msg infractor)
    if target_msg:
        try:
            await context.bot.delete_message(chat_id=msg.chat_id, message_id=target_msg.message_id)
        except TelegramError:
            pass

    # 3) Publicar mensaje visible en el chat
    if n >= limit:
        # Llegó al límite → ejecutar acción
        if action == "ban":
            results = await federate_ban(
                context.bot, db, user_id=target_id,
                reason=f"Límite de warns alcanzado ({n}/{limit}). Último motivo: {reason or '(sin razón)'}",
                rule="warns_limit",
                triggered_in_chat=msg.chat_id, shadow=cfg.shadow,
            )
            ok = sum(1 for v in results.values() if v == "ok")
            text = (
                f"🔨 {mention} ha alcanzado el límite de warns (<b>{n}/{limit}</b>).\n"
                f"<b>Ban federado</b> en {ok} chats."
            )
            if reason:
                text += f"\n💬 Último motivo: {html.escape(reason)}"
        elif action == "kick":
            try:
                await context.bot.ban_chat_member(chat_id=msg.chat_id, user_id=target_id)
                await asyncio.sleep(0.5)
                await context.bot.unban_chat_member(
                    chat_id=msg.chat_id, user_id=target_id, only_if_banned=True,
                )
            except TelegramError as exc:
                log.warning("warn kick fallo: %s", exc)
            text = f"👢 {mention} ha alcanzado el límite (<b>{n}/{limit}</b>). <b>Kick</b>."
        elif action == "mute":
            from telegram import ChatPermissions
            try:
                await context.bot.restrict_chat_member(
                    chat_id=msg.chat_id, user_id=target_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=int(time.time()) + 86400,
                )
            except TelegramError as exc:
                log.warning("warn mute fallo: %s", exc)
            text = f"🤐 {mention} ha alcanzado el límite (<b>{n}/{limit}</b>). <b>Mute 24h</b>."
        else:
            text = f"⚠️ {mention} — Warn <b>{n}/{limit}</b>"
        db.reset_warns(target_id, msg.chat_id)
    else:
        text = f"⚠️ {mention} — Warn <b>{n}/{limit}</b>"
        if reason:
            text += f"\n💬 <b>Motivo:</b> {html.escape(reason)}"

    try:
        sent = await context.bot.send_message(
            chat_id=msg.chat_id, text=text, parse_mode="HTML",
            disable_notification=False,
        )
    except TelegramError as exc:
        log.warning("warn publish fallo: %s", exc)
        return
    # Auto-borrar el mensaje a las N segundos (mismo PUBLIC_QUIP_DELETE_AFTER_S
    # que los quips de ban/kick) para no ensuciar el chat con histórico.
    cfg = context.bot_data.get("cfg")
    delete_after = getattr(cfg, "public_quip_delete_after_s", 10800) if cfg else 10800
    jq = context.application.job_queue
    if jq is not None and delete_after > 0:
        jq.run_once(
            _delete_warn_msg_job, when=delete_after,
            data={"chat_id": msg.chat_id, "message_id": sent.message_id},
            name=f"del_warn_{msg.chat_id}_{sent.message_id}",
        )


async def _delete_warn_msg_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    try:
        await context.bot.delete_message(chat_id=data["chat_id"], message_id=data["message_id"])
    except TelegramError:
        pass


@_admin_only
async def cmd_warns(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    target_id, target_name = _get_target(update)
    if not target_id:
        await msg.reply_text("Responde al mensaje del usuario con /warns.")
        return
    db: DB = context.bot_data["db"]
    warns = db.list_warns(target_id, msg.chat_id)
    if not warns:
        await msg.reply_text(f"Sin warns activos para {html.escape(target_name or str(target_id))}.")
        return
    db.ensure_chat_settings(msg.chat_id)
    settings = db.get_chat_settings(msg.chat_id)
    limit = settings["warns_limit"] or 3
    lines = [f"⚠️ <b>{html.escape(target_name or str(target_id))}</b>: {len(warns)}/{limit} warns"]
    import datetime as _dt
    for w in warns:
        ts = _dt.datetime.fromtimestamp(w["ts"]).strftime("%Y-%m-%d %H:%M")
        r = w["reason"] or "(sin razón)"
        lines.append(f"  [{ts}] {html.escape(r)}")
    await msg.reply_text("\n".join(lines), parse_mode="HTML")


@_admin_only
async def cmd_rmwarn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    target_id, _ = _get_target(update)
    if not target_id:
        await msg.reply_text("Responde al mensaje del usuario con /rmwarn.")
        return
    db: DB = context.bot_data["db"]
    ok = db.remove_last_warn(target_id, msg.chat_id)
    if ok:
        await msg.reply_text("✅ Último warn eliminado.")
    else:
        await msg.reply_text("Sin warns para eliminar.")


@_admin_only
async def cmd_resetwarns(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    target_id, _ = _get_target(update)
    if not target_id:
        await msg.reply_text("Responde al mensaje del usuario con /resetwarns.")
        return
    db: DB = context.bot_data["db"]
    n = db.reset_warns(target_id, msg.chat_id)
    await msg.reply_text(f"✅ {n} warn(s) eliminados.")


@_admin_only
async def cmd_warnlimit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    chat_id = update.effective_chat.id
    db.ensure_chat_settings(chat_id)
    if not context.args:
        s = db.get_chat_settings(chat_id)
        await update.effective_message.reply_text(f"Límite actual: <b>{s['warns_limit']}</b>", parse_mode="HTML")
        return
    if not context.args[0].isdigit():
        await update.effective_message.reply_text("Uso: /warnlimit <N>")
        return
    n = max(1, min(20, int(context.args[0])))
    db.update_chat_setting(chat_id, "warns_limit", n)
    await update.effective_message.reply_text(f"✅ Límite warns = {n}")


@_admin_only
async def cmd_warnaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    chat_id = update.effective_chat.id
    db.ensure_chat_settings(chat_id)
    if not context.args:
        s = db.get_chat_settings(chat_id)
        await update.effective_message.reply_text(f"Acción actual: <b>{s['warns_action']}</b>", parse_mode="HTML")
        return
    action = context.args[0].lower()
    if action not in ("ban", "kick", "mute"):
        await update.effective_message.reply_text("Uso: /warnaction ban|kick|mute")
        return
    db.update_chat_setting(chat_id, "warns_action", action)
    await update.effective_message.reply_text(f"✅ Acción warns = {action}")
