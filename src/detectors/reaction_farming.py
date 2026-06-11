"""Detector de reaction-farming: usuarios que dan likes en ráfaga sin haber escrito nunca.

Patrón: cuenta-bot recién creada o durmiente, su única actividad son reacciones
masivas a mensajes para inflar su perfil. Bot API 7.0+ entrega MessageReactionUpdated.
"""
from __future__ import annotations

import time

from . import Hit


def check(
    user_id: int,
    total_msgs_user: int,
    reactions_in_window: int,
    threshold_count: int,
    threshold_seconds: int,
) -> Hit:
    """Detecta reaction-farming. Criterio del usuario (validado en producción):

    - total_msgs_user == 0 (nunca escribió en ningún chat del bot)
    - reactions_in_window >= threshold_count (default 5 en 60s)

    Es raro que alguien dé 5+ reacciones en <60s sin haber escrito nunca,
    incluso lurkers veteranos. No añadimos guard de 24h porque ese patrón
    es señal fuerte de bot independientemente del tiempo en el grupo.
    """
    if total_msgs_user > 0:
        return Hit.none()
    if reactions_in_window < threshold_count:
        return Hit.none()
    return Hit(
        rule="reaction_farming",
        score=100,
        reason=(
            f"Reaction-farming: {reactions_in_window} reacciones en {threshold_seconds}s "
            f"sin mensajes previos (umbral {threshold_count})"
        ),
        payload={"reactions": reactions_in_window, "window_s": threshold_seconds},
    )


def window_start_ts(threshold_seconds: int) -> float:
    return time.time() - threshold_seconds
