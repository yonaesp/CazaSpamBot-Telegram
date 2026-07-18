"""Detector: primer mensaje es media (foto/video/sticker) — patrón spam 2025-2026.

Patrón típico: cuenta nueva (recién creada, sin foto de perfil propia, sin
username) entra al grupo y su PRIMER mensaje es una imagen promocional
(spam de cripto, casino, OnlyFans, etc.) con caption corto o ninguno.

Por sí solo el detector da score moderado (puede haber humanos que mandan
una foto como primer mensaje legítimo). Combinado con cuenta sospechosa,
sube a score de ban directo.
"""
from __future__ import annotations

from telegram import Message

from ..i18n import t
from . import Hit


def check(
    msg: Message,
    is_first_msg: bool,
    is_suspicious: bool,
    suspicious_reasons: list[str] | None = None,
) -> Hit:
    """Si primer msg con media + cuenta sospechosa → ban.
    Si solo primer msg con media (sin sospecha) → score medio para combinar con otros.
    """
    if not is_first_msg:
        return Hit.none()
    media_type = None
    if msg.photo:
        media_type = t("reason.media_photo")
    elif msg.video:
        media_type = t("reason.media_video")
    elif msg.animation:
        media_type = t("reason.media_gif")
    elif msg.sticker:
        media_type = t("reason.media_sticker")
    elif msg.document:
        media_type = t("reason.media_document")
    elif msg.video_note:
        media_type = t("reason.media_video_note")
    if not media_type:
        return Hit.none()

    caption = (msg.caption or "").strip()
    short_caption = len(caption) < 20

    score = 70  # base
    reasons = [t("reason.fmm_first_media", media_type=media_type)]
    if short_caption:
        score += 20
        reasons.append(t("reason.fmm_short_caption"))
    if is_suspicious:
        # Cuenta sospechosa + media primer msg = patrón spam clarísimo
        score += 50
        if suspicious_reasons:
            reasons.append(t("reason.fmm_suspicious_detail", details=", ".join(suspicious_reasons[:3])))
        else:
            reasons.append(t("reason.fmm_suspicious"))
    return Hit(
        rule="first_msg_media",
        score=score,
        reason=" + ".join(reasons),
        payload={
            "media_type": media_type,
            "caption_len": len(caption),
            "is_suspicious": is_suspicious,
            "suspicious_reasons": suspicious_reasons or [],
        },
    )
