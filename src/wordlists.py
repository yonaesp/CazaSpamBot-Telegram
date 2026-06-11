"""Carga de listas negras editables desde `config/blacklist/`.

Cada archivo es texto plano: un patrón por línea (palabra suelta o regex),
líneas vacías y las que empiezan por `#` se ignoran. Así cualquiera puede
personalizar las palabras/frases que disparan el antispam SIN tocar código.

Si el archivo no existe, se usan los `defaults` pasados (fallback en el código),
de modo que el bot funciona out-of-the-box aunque falte `config/`.
"""
from __future__ import annotations

import re
from pathlib import Path

_BLACKLIST_DIR = Path(__file__).resolve().parent.parent / "config" / "blacklist"


def load_terms(filename: str, defaults: list[str]) -> list[str]:
    """Lee los términos de config/blacklist/<filename> (uno por línea).

    Devuelve `defaults` si el archivo no existe o está vacío de términos útiles.
    """
    try:
        raw = (_BLACKLIST_DIR / filename).read_text(encoding="utf-8")
    except OSError:
        return list(defaults)
    terms = [
        ln.strip() for ln in raw.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    return terms or list(defaults)


def compile_alternation(
    terms: list[str], *, boundaries: bool = True, flags: int = re.IGNORECASE,
) -> re.Pattern:
    """Compila los términos en una alternancia de regex `(?:a|b|c)`.

    Cada término es una alternativa de regex (NO se escapa: se admiten regex).
    Para evitar romper el conteo de coincidencias, usa grupos NO capturantes
    `(?:...)` dentro de tus términos, nunca `(...)`.

    boundaries=True envuelve en `\\b(?:...)\\b` (palabra completa).
    """
    body = "|".join(t for t in terms if t)
    if not body:
        body = r"(?!x)x"  # patrón imposible: no casa nunca
    pattern = rf"\b(?:{body})\b" if boundaries else rf"(?:{body})"
    return re.compile(pattern, flags)


def load_and_compile(
    filename: str, defaults: list[str], *, boundaries: bool = True, flags: int = re.IGNORECASE,
) -> re.Pattern:
    """Atajo: carga los términos del archivo (o defaults) y los compila."""
    return compile_alternation(load_terms(filename, defaults), boundaries=boundaries, flags=flags)
