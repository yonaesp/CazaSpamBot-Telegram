"""Detector: primer mensaje casi sin texto real, dominado por emojis/símbolos.

Patrón de spam de captación de atención: el mensaje es una ristra de emojis
con poco o ningún texto alfabético (a menudo acompañado de media/botones que
la Bot API no siempre entrega). Caso real (aunimwfcbot): texto "🍭🍄 🌟🎨 🌃🌃".

Solo aplica a PRIMEROS mensajes (is_first) para no molestar a veteranos que
mandan "jajaja 😂😂😂". Requiere muchos emojis Y casi nada de texto alfabético.
"""
from __future__ import annotations

from telegram import Message

from . import Hit

# Rango amplio de emojis/pictogramas
_EMOJI_RANGES = (
    (0x1F300, 0x1FAFF), (0x2600, 0x27BF), (0x1F000, 0x1F2FF),
    (0x2B00, 0x2BFF), (0x1F900, 0x1F9FF), (0xFE00, 0xFE0F),
)


def _is_emoji(c: str) -> bool:
    cp = ord(c)
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


def check(msg: Message, is_first_msg: bool = False) -> Hit:
    if not is_first_msg:
        return Hit.none()
    text = (msg.text or msg.caption or "")
    if not text:
        return Hit.none()
    n_emoji = sum(1 for c in text if _is_emoji(c))
    n_alpha = sum(1 for c in text if c.isalpha())
    # Necesitamos varios emojis y casi nada de texto real
    if n_emoji < 3:
        return Hit.none()
    if n_alpha >= 6:  # 6+ letras = hay texto real, probablemente legítimo
        return Hit.none()
    # Muchos emojis dominando el mensaje + texto alfabético ínfimo → spam de atención
    score = 60 if n_emoji >= 5 else 45
    return Hit(
        rule="emoji_only_first_msg",
        score=score,
        reason=f"Primer mensaje casi sin texto real ({n_emoji} emojis, {n_alpha} letras) — captación de atención",
        payload={"n_emoji": n_emoji, "n_alpha": n_alpha},
    )
