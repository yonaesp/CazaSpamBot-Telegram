"""Detector "Join-to-First-Message" delta.

Heurística:
- Humanos típicos: minutos/horas/días entre join y primer msg
- Bots automáticos: <90 segundos (responden inmediato) o múltiplos de 24h (cron)

Solo aplica al PRIMER mensaje del user en el chat.
"""
from __future__ import annotations

from . import Hit


def check(
    is_first_msg: bool,
    delta_seconds: float | None,
) -> Hit:
    if not is_first_msg or delta_seconds is None:
        return Hit.none()
    if delta_seconds < 5:
        return Hit(
            rule="jfm_too_fast",
            score=80,
            reason=f"Primer mensaje a los {int(delta_seconds)}s del join (bot probable)",
            payload={"delta_s": int(delta_seconds)},
        )
    if delta_seconds < 30:
        return Hit(
            rule="jfm_fast",
            score=40,
            reason=f"Primer mensaje a los {int(delta_seconds)}s del join (sospechoso)",
            payload={"delta_s": int(delta_seconds)},
        )
    # Detector de cron pattern: cerca de múltiplos exactos de 24h
    hours = delta_seconds / 3600
    near_day_multiple = abs(hours - round(hours / 24) * 24) < 0.05  # ±3 min
    if near_day_multiple and hours >= 23:
        return Hit(
            rule="jfm_cron",
            score=60,
            reason=f"Primer mensaje exactamente a las {round(hours/24)*24}h del join (patrón cron)",
            payload={"delta_s": int(delta_seconds), "hours": hours},
        )
    return Hit.none()
