"""Detector: cuenta DORMIDA que reaparece mencionando un bot sospechoso.

Patrón de cuenta comprometida/vendida: un usuario que llevaba >1 año sin
escribir reaparece y su PRIMER mensaje tras el silencio es una mención a un
bot (@xxxbot), sin ser respuesta a nadie. Caso real (jonhymontes, 2026-06-06):
cuenta vieja inactiva → menciona @aunimwfcbot (bot porno).

Señales (todas necesarias):
  - El user llevaba >365 días sin escribir (last_msg_ts antiguo).
  - El mensaje menciona un @username cuyo nombre contiene 'bot'.
  - El mensaje NO es respuesta a otro (reply_to_message is None).

Es un patrón muy específico → ban directo (cuenta hackeada/vendida).
"""
from __future__ import annotations

import re
import time

from telegram import Message, MessageEntity

from . import Hit

DORMANT_DAYS = 365

# @username que termina o contiene 'bot' (insensible a mayúsculas)
_BOT_MENTION_RE = re.compile(r"@([A-Za-z0-9_]{3,32})", re.IGNORECASE)

# Bots LEGÍTIMOS conocidos: si un user dormido vuelve y menciona uno de estos
# (p.ej. para pedir ayuda), NO es spam. Whitelist anti-falso-positivo.
_LEGIT_BOTS = frozenset({
    "grouphelpbot", "userinfobot", "combot", "combot_anti_spam_bot",
    "gif", "sticker", "vote", "like", "pollbot", "directlinkbot",
    "rosebot", "missrose_bot", "shieldy_bot", "safeguard", "spambot",
    "botfather", "cazaspambot", "getidsbot", "username_to_id_bot",
})


def _mentions_a_bot(msg: Message) -> str | None:
    """Devuelve el @username del primer bot mencionado (nombre contiene 'bot'),
    EXCLUYENDO bots legítimos conocidos."""
    text = msg.text or msg.caption or ""
    candidatos: list[str] = []
    # 1) Por entidades MENTION (texto @username)
    for ent in (msg.entities or []) + (msg.caption_entities or []):
        if ent.type == MessageEntity.MENTION:
            candidatos.append(text[ent.offset:ent.offset + ent.length].lstrip("@"))
    # 2) Fallback regex sobre el texto plano
    for m in _BOT_MENTION_RE.finditer(text):
        candidatos.append(m.group(1))
    for uname in candidatos:
        if "bot" in uname.lower() and uname.lower() not in _LEGIT_BOTS:
            return uname
    return None


def check(
    msg: Message,
    last_msg_ts: float | None,
    now: float | None = None,
) -> Hit:
    """Args:
    last_msg_ts: timestamp del ÚLTIMO mensaje previo del user (antes de este).
                 None si nunca escribió (no aplica este detector).
    """
    if last_msg_ts is None:
        return Hit.none()  # sin historial previo, no es "cuenta dormida que vuelve"
    now = now or time.time()
    dormant_days = (now - last_msg_ts) / 86400
    if dormant_days < DORMANT_DAYS:
        return Hit.none()
    # No aplica si es respuesta a alguien (conversación legítima)
    if msg.reply_to_message is not None:
        return Hit.none()
    bot_uname = _mentions_a_bot(msg)
    if not bot_uname:
        return Hit.none()
    return Hit(
        rule="dormant_bot_mention",
        score=120,
        reason=(
            f"Cuenta dormida {int(dormant_days)}d reaparece mencionando @{bot_uname} "
            f"(bot) sin responder a nadie — patrón de cuenta hackeada/vendida"
        ),
        payload={"dormant_days": int(dormant_days), "bot_mentioned": bot_uname},
    )
