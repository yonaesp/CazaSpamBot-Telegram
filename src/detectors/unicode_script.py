"""Detector de script Unicode no-permitido en primeros mensajes.

Política: si en los primeros N mensajes del usuario aparece un ratio > X de
caracteres en scripts NO permitidos (chino, cirílico, árabe, hangul, etc.),
es señal fuerte de spam dirigido a otro idioma.

Implementación: clasificación por rangos Unicode con `unicodedata`. Cero deps,
microsegundos por mensaje.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from . import Hit

# Rangos Unicode (start, end, script_name). Solo los relevantes para detección.
# Ref: https://www.unicode.org/Public/UCD/latest/ucd/Blocks.txt
_SCRIPT_RANGES: tuple[tuple[int, int, str], ...] = (
    # Latin
    (0x0041, 0x007A, "latin"),  # A-Z, a-z (con gaps internos, filtrado abajo)
    (0x00C0, 0x024F, "latin"),  # Latin-1 Supplement + Latin Extended-A/B
    (0x1E00, 0x1EFF, "latin"),  # Latin Extended Additional
    # Cyrillic
    (0x0400, 0x04FF, "cyrillic"),
    (0x0500, 0x052F, "cyrillic"),
    # Greek
    (0x0370, 0x03FF, "greek"),
    # Hebrew
    (0x0590, 0x05FF, "hebrew"),
    # Arabic
    (0x0600, 0x06FF, "arabic"),
    (0x0750, 0x077F, "arabic"),
    (0x08A0, 0x08FF, "arabic"),
    # Devanagari (hindi)
    (0x0900, 0x097F, "devanagari"),
    # CJK
    (0x3000, 0x303F, "han"),       # CJK Symbols and Punctuation
    (0x3400, 0x4DBF, "han"),       # CJK Ext A
    (0x4E00, 0x9FFF, "han"),       # CJK Unified Ideographs
    (0x20000, 0x2A6DF, "han"),     # CJK Ext B
    # Japanese
    (0x3040, 0x309F, "hiragana"),
    (0x30A0, 0x30FF, "katakana"),
    # Korean
    (0xAC00, 0xD7AF, "hangul"),
    (0x1100, 0x11FF, "hangul"),
)


def script_of(char: str) -> str | None:
    """Devuelve el nombre del script Unicode del carácter, o None si es neutro
    (números, puntuación ASCII, espacios, emojis, símbolos)."""
    cp = ord(char)
    # ASCII básico (excepto letras) y espacios → neutro
    if cp < 0x80:
        if char.isalpha():
            return "latin"
        return None
    # No clasificamos símbolos/emojis/marks como un script
    cat = unicodedata.category(char)
    if cat[0] in ("N", "P", "S", "Z", "M", "C"):
        # N=numero, P=puntuación, S=símbolo (incluye emojis), Z=separador,
        # M=combining mark, C=control. Todos neutros para script detection.
        return None
    for start, end, name in _SCRIPT_RANGES:
        if start <= cp <= end:
            return name
    # Letra fuera de los rangos conocidos → "other"
    if char.isalpha():
        return "other"
    return None


def script_distribution(text: str) -> dict[str, int]:
    """Cuenta caracteres por script. Solo letras (ignora puntuación/espacios)."""
    counts: dict[str, int] = {}
    for ch in text:
        sc = script_of(ch)
        if sc:
            counts[sc] = counts.get(sc, 0) + 1
    return counts


def non_allowed_ratio(text: str, allowed: Iterable[str]) -> tuple[float, str]:
    """Devuelve (ratio_no_permitido, script_dominante_no_permitido)."""
    counts = script_distribution(text)
    if not counts:
        return 0.0, ""
    total = sum(counts.values())
    allowed_set = {s.lower() for s in allowed}
    bad = {k: v for k, v in counts.items() if k not in allowed_set}
    if not bad:
        return 0.0, ""
    bad_total = sum(bad.values())
    dominant = max(bad, key=bad.get)
    return bad_total / total, dominant


def check(
    text: str | None,
    is_first_msgs: bool,
    allowed_scripts: Iterable[str],
    threshold: float,
    score_when_first: int = 100,
    score_when_late: int = 30,
) -> Hit:
    if not text:
        return Hit.none()
    ratio, dominant = non_allowed_ratio(text, allowed_scripts)
    if ratio < threshold:
        return Hit.none()
    score = score_when_first if is_first_msgs else score_when_late
    return Hit(
        rule="non_allowed_script",
        score=score,
        reason=f"Script no permitido «{dominant}» (ratio={ratio:.0%}) en {'primer mensaje' if is_first_msgs else 'mensaje tardío'}",
        payload={"ratio": ratio, "dominant_script": dominant, "first_msg": is_first_msgs},
    )
