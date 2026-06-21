"""Convierte score acumulado en acción concreta."""
from __future__ import annotations

from dataclasses import dataclass

from .detectors import Hit


@dataclass(frozen=True)
class Decision:
    action: str  # ban | kick | mute | delete | noop
    score: int
    rule: str
    reason: str
    payload: dict


def combine(hits: list[Hit]) -> tuple[int, list[Hit]]:
    real_hits = [h for h in hits if h]
    return sum(h.score for h in real_hits), real_hits


def decide(
    hits: list[Hit],
    ban_score: int,
    kick_score: int,
    mute_score: int,
    first_msg_attack_action: str,
    is_first_msg_attack: bool,
) -> Decision:
    score, real_hits = combine(hits)
    if not real_hits:
        return Decision(action="noop", score=0, rule="", reason="", payload={})

    # Override del usuario: si dispara first-msg-attack y configuró acción específica.
    if is_first_msg_attack:
        action_map = {"ban": "ban", "kick": "kick", "mute_24h": "mute", "delete_only": "delete", "shadow": "noop"}
        forced = action_map.get(first_msg_attack_action, "ban")
        rule = "+".join(h.rule for h in real_hits)
        reason = " | ".join(h.reason for h in real_hits)
        payload = {h.rule: h.payload for h in real_hits if h.payload}
        return Decision(action=forced, score=score, rule=rule, reason=reason, payload=payload)

    if score >= ban_score:
        action = "ban"
    elif score >= kick_score:
        action = "kick"
    elif score >= mute_score:
        action = "mute"
    else:
        # Score por debajo del umbral de mute: señal(es) demasiado débil(es) para
        # actuar. NO se borra el mensaje (antes sí, y eso hacía que un detector
        # de comportamiento como jfm_fast (30) borrara mensajes inocentes como
        # "Hola"). Las señales débiles solo cuentan al SUMARSE con otras.
        action = "noop"

    rule = "+".join(h.rule for h in real_hits)
    reason = " | ".join(h.reason for h in real_hits)
    payload = {h.rule: h.payload for h in real_hits if h.payload}
    return Decision(action=action, score=score, rule=rule, reason=reason, payload=payload)
