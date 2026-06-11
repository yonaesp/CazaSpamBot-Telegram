"""Detector: usuario nuevo que REENVÍA un mensaje desde un canal/bot externo
en su primer mensaje o en los primeros minutos tras unirse.

Patrón de spam clásico:
 1. Cuenta nueva entra al grupo.
 2. En su primer mensaje (o pocos segundos/minutos después) reenvía contenido
    promocional desde un canal externo: estafa, criptomonedas, contenido adulto,
    promoción de otro grupo, etc.
 3. Los usuarios reales casi nunca reenvían contenido de canales como primer
    aporte: primero saludan, hacen una pregunta o aportan algo propio.

Por tanto, "primer mensaje = forward desde canal/bot" es señal muy fuerte de spam.
"""
from __future__ import annotations

import time

from telegram import Message

from . import Hit

# Ventana en segundos desde el primer_seen del user para que un forward cuente
# como "primeros minutos" (3 min por defecto).
EARLY_WINDOW_S = 180


def check(
    msg: Message,
    is_first_msg: bool,
    seconds_since_first_seen: float | None = None,
) -> Hit:
    """Detecta forward desde canal/bot en primer mensaje o primeros 3 min.

    Args:
      msg: el mensaje de Telegram.
      is_first_msg: True si el bot lo considera primer mensaje (msg_count<=window).
      seconds_since_first_seen: segundos desde que el bot vio al user por primera
        vez. None si desconocido.
    """
    in_early_window = (
        seconds_since_first_seen is not None
        and seconds_since_first_seen <= EARLY_WINDOW_S
    )
    if not is_first_msg and not in_early_window:
        return Hit.none()

    # PTB 21+: forward_origin (preferido). Fallbacks legacy: forward_from_chat,
    # forward_from, forward_sender_name.
    origin = getattr(msg, "forward_origin", None)
    fwd_chat = getattr(msg, "forward_from_chat", None)
    fwd_user = getattr(msg, "forward_from", None)
    fwd_sender_name = getattr(msg, "forward_sender_name", None)

    if not (origin or fwd_chat or fwd_user or fwd_sender_name):
        return Hit.none()

    origin_type: str = "unknown"
    origin_name: str | None = None

    if fwd_chat is not None:
        origin_type = fwd_chat.type or "channel"  # channel, supergroup, group
        origin_name = fwd_chat.username or fwd_chat.title
    elif fwd_user is not None:
        origin_type = "bot" if getattr(fwd_user, "is_bot", False) else "user"
        origin_name = fwd_user.username or fwd_user.first_name
    elif fwd_sender_name:
        origin_type = "hidden_user"
        origin_name = fwd_sender_name
    elif origin is not None:
        # PTB ≥21 — origin puede ser MessageOriginChannel / MessageOriginUser
        # / MessageOriginHiddenUser. Reflexionamos sobre type field.
        otype = getattr(origin, "type", "")
        if otype == "channel":
            origin_type = "channel"
            ch = getattr(origin, "chat", None)
            origin_name = (ch.username or ch.title) if ch else None
        elif otype == "user":
            u = getattr(origin, "sender_user", None)
            origin_type = "bot" if (u and getattr(u, "is_bot", False)) else "user"
            origin_name = (u.username or u.first_name) if u else None
        elif otype == "hidden_user":
            origin_type = "hidden_user"
            origin_name = getattr(origin, "sender_user_name", None)
        elif otype == "chat":
            origin_type = "chat"
            sc = getattr(origin, "sender_chat", None)
            origin_name = (sc.username or sc.title) if sc else None

    # Severidad:
    # - Forward desde channel en primer msg → BAN directo (score 100)
    # - Forward desde bot en primer msg → BAN (score 95)
    # - Forward desde user/hidden_user en primer msg → KICK (score 80)
    if origin_type in ("channel", "chat"):
        score = 100
        sev = "forward de CANAL en primer mensaje"
    elif origin_type == "bot":
        score = 95
        sev = "forward de BOT en primer mensaje"
    else:
        score = 80
        sev = f"forward de {origin_type} en primer mensaje"

    # Si está en la ventana temprana pero ya tiene varios mensajes, suaviza un poco
    if not is_first_msg and in_early_window:
        score = max(70, score - 15)
        sev += f" (dentro de {EARLY_WINDOW_S}s tras primer seen)"

    reasons = [sev]
    if origin_name:
        reasons.append(f"origen: {origin_name}")

    return Hit(
        rule="forward_first_msg",
        score=score,
        reason=" + ".join(reasons),
        payload={
            "origin_type": origin_type,
            "origin_name": origin_name,
            "is_first_msg": is_first_msg,
            "seconds_since_first_seen": seconds_since_first_seen,
        },
    )
