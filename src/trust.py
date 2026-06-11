"""Presentación de niveles 1-10.

Internamente el bot acumula scores (0-100 de confianza del usuario, 0-200+ de
spam de un mensaje). Esos números sueltos confunden, así que de cara al admin
se muestran como un nivel del 1 al 10:

  - CONFIANZA del usuario: 10 = máxima confianza (veterano), 1 = recién llegado.
  - SPAM de un mensaje:     10 = clarísimamente spam, 1 = limpio.

La lógica interna sigue usando los scores 0-100; esto es solo display.
"""
from __future__ import annotations


def score_to_level(score: int, *, full: int = 100) -> int:
    """Convierte un score interno a un nivel 1-10. `full` = score que vale 10."""
    if score <= 0:
        return 1
    return max(1, min(10, round(score / full * 10)))


def trust_level(score_0_100: int) -> int:
    """Nivel de CONFIANZA del usuario (10 = máxima confianza)."""
    return score_to_level(score_0_100, full=100)


def spam_level(score: int, *, ban_score: int = 100) -> int:
    """Nivel de SPAM de un mensaje (10 = alcanza el umbral de ban)."""
    return score_to_level(score, full=ban_score)


def _emoji(level: int, *, high_is_good: bool) -> str:
    if high_is_good:
        return "🟢" if level >= 7 else ("🟡" if level >= 4 else "🔴")
    return "🔴" if level >= 7 else ("🟡" if level >= 4 else "🟢")


def render_trust(score_0_100: int) -> str:
    """Ej: '🟢 8/10'. Confianza del usuario."""
    lvl = trust_level(score_0_100)
    return f"{_emoji(lvl, high_is_good=True)} {lvl}/10"


def render_spam(score: int, *, ban_score: int = 100) -> str:
    """Ej: '🔴 9/10'. Nivel de spam de un mensaje."""
    lvl = spam_level(score, ban_score=ban_score)
    return f"{_emoji(lvl, high_is_good=False)} {lvl}/10"
