"""Detector: cuenta Premium + nueva (sin foto/foto reciente) + link en primer mensaje.

Spammers 2025 usan Telegram Premium para parecer legítimos. Si la cuenta es premium
PERO acaba de crearse o no tiene foto, y mete un link en su primer mensaje, es una
combinación muy típica de spam.
"""
from __future__ import annotations

from urllib.parse import urlparse

from telegram import Message, MessageEntity

from . import Hit


def _has_link(msg: Message) -> bool:
    text = msg.text or msg.caption or ""
    if "://" in text or "t.me/" in text:
        return True
    for ent in (msg.entities or []) + (msg.caption_entities or []):
        if ent.type in (MessageEntity.URL, MessageEntity.TEXT_LINK):
            return True
    return False


def check(
    msg: Message,
    is_first_msg: bool,
    user_is_premium: bool,
    user_signals_age_days: int | None,
    user_signals_photo_count: int,
) -> Hit:
    """Devuelve hit si: premium + nueva (sin foto o foto<30d) + link en primer msg."""
    if not is_first_msg:
        return Hit.none()
    if not user_is_premium:
        return Hit.none()
    if not _has_link(msg):
        return Hit.none()
    # "Nueva" = sin foto O foto <30 días
    is_new = (user_signals_photo_count == 0) or (
        user_signals_age_days is not None and user_signals_age_days < 30
    )
    if not is_new:
        return Hit.none()
    return Hit(
        rule="premium_new_link",
        score=80,
        reason="Premium + cuenta nueva + link en primer mensaje (patrón spam 2025)",
        payload={
            "is_premium": True,
            "photo_count": user_signals_photo_count,
            "age_days": user_signals_age_days,
        },
    )
