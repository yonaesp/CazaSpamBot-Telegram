"""Sistema de reporte público vía @admin.

Cuando un usuario escribe @admin (típicamente respondiendo a un mensaje
sospechoso de otro usuario), Telegram avisa nativamente a todos los admins
del grupo. Además mi bot:

1. Responde al reporter: "🙏 Un admin lo revisará, gracias por avisar"
2. Auto-borra esa confirmación a los 60 segundos
3. Registra el reporte en `admin_reports` con el msg_id reportado

Si después un admin (manual o vía bot) borra el mensaje reportado, el bridge
Telethon (events.MessageDeleted) detecta el delete y este módulo:

4. Borra el mensaje @admin del reporter (sin warn ni strike)
5. Publica un thanks gracioso al reporter
6. Marca el reporte como resuelto en DB

El thanks se auto-borra a los 5 min para no ensuciar el grupo.
"""
from __future__ import annotations

import html
import logging
import random
import re
from typing import Optional

from telegram import Message
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .db import DB

log = logging.getLogger(__name__)

# Detección de @admin como mención (con/sin entity)
_ADMIN_MENTIONS = ("@admin", "@admins", "@administrador", "@administradores")
_ADMIN_RE = re.compile(r"(?<![A-Za-z0-9_])@(?:admin|admins|administrador|administradores)(?![A-Za-z0-9_])", re.IGNORECASE)

CONFIRM_TTL_S = 60          # Auto-borra confirm tras 1 min
THANKS_TTL_S = 5 * 60       # Auto-borra thanks tras 5 min

_CONFIRM_TEMPLATES = [
    "🙏 Un administrador revisará tu mensaje. Gracias por avisar.",
    "👮 Aviso recibido. Un admin lo revisará en breve. Gracias.",
    "📩 Reporte registrado. Un administrador lo revisará pronto.",
    "✅ Aviso enviado a los admins. Gracias por colaborar.",
    "🛎️ He notificado a los admins. Lo revisarán enseguida.",
]

_THANKS_WARN_TEMPLATES = [
    "🎉 <b>{reporter}</b>, gracias por avisar. El usuario recibió un warning y el mensaje fue borrado. ¡Buen ojo!",
    "👏 <b>{reporter}</b>, gracias por reportar. Avisamos al usuario y borramos el mensaje. Sigue así.",
    "🙌 <b>{reporter}</b>, mensaje retirado y aviso al usuario. Gracias por contribuir a las normas del grupo.",
    "✊ <b>{reporter}</b>, gracias por avisar. Warning entregado.",
    "🛡️ <b>{reporter}</b>, gracias por mantener el orden. El usuario fue avisado.",
    "📋 <b>{reporter}</b>, gracias por reportar. Mensaje fuera, warning al usuario.",
    "🤝 <b>{reporter}</b>, gracias por la vigilancia. Aviso enviado al usuario.",
    "🌱 <b>{reporter}</b>, gracias. Le hemos llamado la atención al usuario.",
    "🎯 <b>{reporter}</b>, buen ojo. Avisado el usuario, mensaje borrado.",
]


_THANKS_TEMPLATES = [
    "🎉 <b>{reporter}</b>, tu reporte fue revisado y ese usuario ha sido expulsado. Gracias por colaborar a mantener el grupo limpio 🧹",
    "👏 <b>{reporter}</b>, gracias por avisar. Ese usuario ya está fuera. Un poquito de gentucilla menos.",
    "🙌 <b>{reporter}</b>, reporte tramitado y usuario expulsado. Gracias por hacer del grupo un sitio mejor.",
    "🤝 <b>{reporter}</b>, gracias por avisar a tiempo. Spammer al exterior. ¡Que tengas buen día!",
    "🏆 <b>{reporter}</b>, vigilancia 10/10. Spammer expulsado por tu aviso.",
    "✊ <b>{reporter}</b>, gracias. Ese ya no vuelve.",
    "🧹 Reporte de <b>{reporter}</b> procesado. Un spammer menos en el grupo, gracias!",
    "🛡️ <b>{reporter}</b>, gracias por estar atento. Limpieza realizada.",
    "🫡 Misión cumplida gracias a <b>{reporter}</b>. Spammer expulsado.",
    "🎯 Reporte de <b>{reporter}</b> en el blanco. Ese usuario al exterior.",
    "🌍 <b>{reporter}</b>, gracias por contribuir a un mundo más limpio de spammers como ese. ¡Un saludo!",
    "✨ Gracias <b>{reporter}</b>, un espécimen menos contaminando el grupo.",
    "🚮 <b>{reporter}</b>, gracias por tirar la basura. Ese ya no vuelve.",
    "💎 <b>{reporter}</b>, tu vigilancia hace el grupo mejor. Spammer fuera.",
    "🦸 <b>{reporter}</b> al rescate. Spammer expulsado, grupo agradecido.",
    "🌟 <b>{reporter}</b>, gracias por reportar. Una cuenta zombi menos en el mundo.",
    "🏅 <b>{reporter}</b>, gracias por colaborar en la limpieza. Ese ya no nos molestará.",
    "🎖️ Medalla al civismo para <b>{reporter}</b>. Spammer expulsado por tu aviso.",
    "🌿 <b>{reporter}</b>, gracias por mantener el grupo libre de alimañas digitales.",
    "🧼 Lavado y planchado gracias a <b>{reporter}</b>. Personaje malvado fuera.",
    "🎬 <b>{reporter}</b>, gracias por avisar. Telón cerrado para ese personaje.",
    "🌬️ Aire fresco gracias a <b>{reporter}</b>. Cuenta indeseable fuera del grupo.",
    "🐦 Pajarito <b>{reporter}</b> cantó a tiempo. Spammer al exterior.",
]


def contains_admin_mention(msg: Message) -> bool:
    """True si el mensaje contiene @admin como mención (en texto o entidades)."""
    text = msg.text or msg.caption or ""
    if not text:
        return False
    return bool(_ADMIN_RE.search(text))


def _format_reporter(user) -> str:
    """Identifica al reporter sin link clicable. first_name (id: N)."""
    nombre = (user.first_name or "user").strip()[:40]
    nombre = html.escape(nombre)
    return f"{nombre} (id: <code>{user.id}</code>)"


async def handle_admin_mention(
    context: ContextTypes.DEFAULT_TYPE,
    db: DB,
    msg: Message,
) -> None:
    """Procesa un mensaje con @admin: responde al reporter y registra el reporte."""
    reporter = msg.from_user
    if not reporter:
        return
    # Ignorar si es el propio admin del bot (no necesita auto-respuesta)
    from .config import Config
    cfg: Config = context.bot_data["cfg"]
    if reporter.id == cfg.admin_user_id:
        return

    reported = msg.reply_to_message
    if reported:
        reported_msg_id = reported.message_id
        reported_user_id = reported.from_user.id if reported.from_user else None
    else:
        # Heurística: si no hay reply explícito, asumir el mensaje INMEDIATAMENTE ANTERIOR
        # (msg_id - 1). En supergrupos los message_id son secuenciales por chat.
        # No siempre es exacto (puede ser de otro user), pero como tracking funciona:
        # si NADIE borra ese msg_id-1, el cascade no dispara, sin efectos secundarios.
        reported_msg_id = msg.message_id - 1 if msg.message_id > 1 else None
        reported_user_id = None
        log.info(
            "admin_report sin reply explícito, asumiendo msg_id %s como reportado (chat=%s)",
            reported_msg_id, msg.chat_id,
        )

    # Reacción ✍️ al mensaje del reporter (feedback visual rápido sin ensuciar)
    try:
        await context.bot.set_message_reaction(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            reaction=["✍"],
        )
    except TelegramError as exc:
        log.debug("set_message_reaction fallo: %s", exc)

    # Confirmar al reporter
    confirm_text = random.choice(_CONFIRM_TEMPLATES)
    bot_msg_id = None
    try:
        sent = await context.bot.send_message(
            chat_id=msg.chat_id,
            text=confirm_text,
            reply_to_message_id=msg.message_id,
            disable_notification=True,
            allow_sending_without_reply=True,
        )
        bot_msg_id = sent.message_id
    except TelegramError as exc:
        log.warning("admin_report confirm send fallo: %s", exc)

    # Registrar tracking
    db.add_admin_report(
        chat_id=msg.chat_id,
        reporter_msg_id=msg.message_id,
        reporter_user_id=reporter.id,
        reporter_username=reporter.username,
        reported_msg_id=reported_msg_id,
        reported_user_id=reported_user_id,
        bot_confirm_msg_id=bot_msg_id,
    )

    # Auto-delete confirm a 1 min
    if bot_msg_id:
        jq = context.application.job_queue
        if jq:
            jq.run_once(
                _delete_confirm_job, when=CONFIRM_TTL_S,
                data={"chat_id": msg.chat_id, "msg_id": bot_msg_id},
                name=f"del_admin_confirm_{msg.chat_id}_{bot_msg_id}",
            )
    log.info(
        "admin_report registered: reporter=%s msg=%s reported_msg=%s",
        reporter.id, msg.message_id, reported_msg_id,
    )

    # Reenviar al admin DM (ADMIN_USER_ID) el mensaje reportado para revisión
    if cfg.admin_user_id and reported_msg_id:
        try:
            await context.bot.copy_message(
                chat_id=cfg.admin_user_id,
                from_chat_id=msg.chat_id,
                message_id=reported_msg_id,
            )
            chat_title = msg.chat.title or str(msg.chat_id)
            reporter_disp = (
                f"@{reporter.username}" if reporter.username
                else (reporter.first_name or f"id {reporter.id}")
            )
            via = "reply explícito" if reported else "msg anterior (sin reply)"
            ctx_text = (
                f"🚨 <b>@admin reportado</b>\n"
                f"📍 Chat: {html.escape(chat_title)}\n"
                f"👤 Reporter: {html.escape(reporter_disp)} (<code>{reporter.id}</code>)\n"
                f"🎯 Mensaje reportado: <code>{reported_msg_id}</code> ({via})\n"
                f"👤 Autor del msg: <code>{reported_user_id or '?'}</code>"
            )
            await context.bot.send_message(
                chat_id=cfg.admin_user_id, text=ctx_text, parse_mode="HTML",
            )
        except TelegramError as exc:
            log.debug("admin_report copy to admin DM fallo: %s", exc)


async def _delete_confirm_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    try:
        await context.bot.delete_message(chat_id=data["chat_id"], message_id=data["msg_id"])
    except TelegramError:
        pass


async def on_reported_message_deleted(
    bot,
    db: DB,
    chat_id: int,
    deleted_msg_id: int,
) -> None:
    """Callback desde telethon_bridge cuando se borra un mensaje.

    Si coincide con algún admin_report no resuelto, hace cascade: borra el
    mensaje del reporter, borra la confirmación inicial y publica thanks.
    """
    report = db.find_admin_report_by_reported(chat_id, deleted_msg_id)
    if not report:
        return
    # Borrar mensaje del reporter (su @admin)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=report["reporter_msg_id"])
    except TelegramError:
        pass
    # Borrar confirmación inicial si sigue
    if report["bot_confirm_msg_id"]:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=report["bot_confirm_msg_id"])
        except TelegramError:
            pass
    # Publicar thanks — usar first_name si lo tenemos guardado, sino "usuario"
    # SIN link al perfil del reporter (no necesita visibilidad pública)
    rep_uid = report["reporter_user_id"]
    # reporter_username puede contener first_name si lo guardamos en su día
    # En este caso solo tenemos username. Si existe, lo usamos como referencia
    # textual (NO clicable, sin @, solo texto plano)
    if report["reporter_username"]:
        # Mostramos como referencia neutra, sin @ que abra perfil
        reporter_label = f"<i>{html.escape(report['reporter_username'])}</i> (id: <code>{rep_uid}</code>)"
    else:
        reporter_label = f"usuario (id: <code>{rep_uid}</code>)"
    # Elegir template según action_taken (warn/delete → "avisado", ban/kick → "expulsado")
    try:
        action_taken = report["action_taken"]
    except (KeyError, IndexError):
        action_taken = None
    if action_taken in ("warn", "delete"):
        templates = _THANKS_WARN_TEMPLATES
    else:
        templates = _THANKS_TEMPLATES
    thanks_text = random.choice(templates).format(reporter=reporter_label)
    thanks_msg_id = None
    try:
        sent = await bot.send_message(
            chat_id=chat_id, text=thanks_text,
            parse_mode="HTML", disable_notification=True,
        )
        thanks_msg_id = sent.message_id
        log.info(
            "admin_report thanks publicado: chat=%s reporter_uid=%s",
            chat_id, report["reporter_user_id"],
        )
    except TelegramError as exc:
        log.warning("admin_report thanks fallo: %s", exc)

    db.resolve_admin_report(chat_id, report["reporter_msg_id"])

    # Programar borrado del thanks a los 5 min (lo hace el job_queue del bot)
    # Como esto se llama desde Telethon (sin context), necesitamos otra vía.
    # Solución: lo registramos en gentle_warnings para que el cleanup nightly lo limpie
    # si quedara. Pero mejor: programar via Bot API "deleteMessage" en N segundos
    # vía un job en main_app. Por simplicidad: usar aiohttp con asyncio.sleep en background.
    if thanks_msg_id:
        import asyncio
        asyncio.create_task(_delayed_delete(bot, chat_id, thanks_msg_id, THANKS_TTL_S))


async def _delayed_delete(bot, chat_id: int, msg_id: int, delay: int) -> None:
    import asyncio
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass
