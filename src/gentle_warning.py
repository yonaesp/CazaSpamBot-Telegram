"""Aviso suave (trust graduation): users con >N mensajes y >M días reciben un
recordatorio amable de leer las normas en lugar de ban directo cuando disparan
external_mention u otras reglas borderline.

El aviso responde al mensaje del usuario (reply_to_message_id) y se auto-borra
a los 5 min. Si el usuario borra su mensaje antes, el aviso también se borra
gracias al listener Telethon MessageDeleted (ver telethon_bridge.py).
"""
from __future__ import annotations

import html
import logging
import random
from typing import Optional

from telegram import Message
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .db import DB

log = logging.getLogger(__name__)


# Defaults trust
TRUST_MIN_MSGS = 10
TRUST_MIN_DAYS = 10
GENTLE_DELETE_AFTER_S = 300  # 5 min


_GENTLE_TEMPLATES = [
    "👋 Hola {name}. Recuerda revisar las <b>normas del grupo</b> antes de compartir enlaces o mencionar a otros chats. Si lo que has puesto cumple las normas, ignora este mensaje.",
    "ℹ️ {name}, el bot ha detectado un patrón borderline en tu mensaje. Echa un ojo a las <b>normas</b> por si acaso. (Este aviso desaparece solo en 5 min)",
    "🤖 {name}, te he marcado pero como eres miembro habitual no actúo. Repasa las <b>normas</b> y, si está OK, todo bien.",
]


def is_trusted(db: DB, chat_id: int, user_id: int,
               min_msgs: int = TRUST_MIN_MSGS, min_days: int = TRUST_MIN_DAYS) -> bool:
    msg_count, days = db.user_trust_metrics(chat_id, user_id)
    if msg_count < min_msgs:
        return False
    if days is None or days < min_days:
        return False
    return True


def _format_name(user) -> str:
    """Identifica al user sin link clicable a su perfil (evita dar visibilidad
    a perfiles con contenido inapropiado). Formato: first_name (id: N)."""
    nombre = (user.first_name or "user").strip()[:40]
    nombre = html.escape(nombre)
    return f"{nombre} (id: <code>{user.id}</code>)"


async def send(
    context: ContextTypes.DEFAULT_TYPE,
    db: DB,
    msg: Message,
    reason_hint: str = "",
) -> Optional[int]:
    """Envía aviso suave en respuesta al mensaje del usuario.

    Devuelve el message_id del aviso o None si falla.
    Programa borrado a 5 min y registra en gentle_warnings para borrar
    en cascada si el user borra su msg.
    """
    user = msg.from_user
    if not user:
        return None
    template = random.choice(_GENTLE_TEMPLATES)
    text = template.format(name=_format_name(user))
    if reason_hint:
        text += f"\n<i>Motivo detectado: {html.escape(reason_hint)}</i>"
    try:
        sent = await context.bot.send_message(
            chat_id=msg.chat_id,
            text=text,
            parse_mode="HTML",
            reply_to_message_id=msg.message_id,
            disable_notification=True,
            allow_sending_without_reply=True,
        )
    except TelegramError as exc:
        log.warning("gentle_warning send fallo: %s", exc)
        return None

    db.add_gentle_warning(
        chat_id=msg.chat_id,
        user_msg_id=msg.message_id,
        bot_msg_id=sent.message_id,
        user_id=user.id,
    )

    # Job auto-delete 5 min
    jq = context.application.job_queue
    if jq:
        jq.run_once(
            _delete_gentle_job, when=GENTLE_DELETE_AFTER_S,
            data={"chat_id": msg.chat_id, "user_msg_id": msg.message_id, "bot_msg_id": sent.message_id},
            name=f"del_gentle_{msg.chat_id}_{sent.message_id}",
        )
    return sent.message_id


async def _delete_gentle_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    db: DB = context.bot_data["db"]
    try:
        await context.bot.delete_message(chat_id=data["chat_id"], message_id=data["bot_msg_id"])
    except TelegramError:
        pass
    db.delete_gentle_warning(data["chat_id"], data["user_msg_id"])
