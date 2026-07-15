"""Internacionalización (i18n) del bot. Idioma GLOBAL de la instancia.

El idioma se resuelve al arrancar (ver main): pref persistida > env BOT_LANG > locale
del sistema > 'es'. Se cambia en caliente con /idioma (persiste). `t(key, **fmt)`
devuelve el texto en el idioma actual, con fallback al español y, si falta, a la clave.

Migración incremental: mientras un texto no esté en los paquetes de idioma sigue
hardcodeado; `t()` con una clave inexistente devuelve la clave (visible = pendiente).
"""
from __future__ import annotations

import logging
import os

from .locales import STRINGS

log = logging.getLogger(__name__)

SUPPORTED = ("es", "en")
DEFAULT = "es"
_current = DEFAULT


def detect_system_lang() -> str:
    """Idioma sugerido a partir de las variables de entorno estándar del sistema
    (BOT_LANG tiene prioridad; luego LC_ALL/LC_MESSAGES/LANG/LANGUAGE). Se toma el
    código de 2 letras; si no es uno soportado (p.ej. C.UTF-8/POSIX) → DEFAULT.

    NO se usa `locale.getlocale()`: devuelve valores espurios (p.ej. 'en_US') en
    sistemas con locale neutro C.UTF-8, lo que haría que el bot saliera en inglés
    sin que nadie lo pidiera. Las variables de entorno son la señal fiable.
    """
    for var in ("BOT_LANG", "LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        code = (os.getenv(var) or "").strip().lower()[:2]
        if code in SUPPORTED:
            return code
    return DEFAULT


def set_lang(lang: str | None) -> str:
    """Fija el idioma global (normalizado). Devuelve el idioma efectivo."""
    global _current
    code = (lang or "").strip().lower()[:2]
    _current = code if code in SUPPORTED else DEFAULT
    return _current


def current_lang() -> str:
    return _current


def is_supported(lang: str | None) -> bool:
    return (lang or "").strip().lower()[:2] in SUPPORTED


def t(key: str, lang: str | None = None, **fmt) -> str:
    """Texto traducido: idioma dado o el global; fallback ES y luego la propia clave."""
    lg = (lang or _current)
    s = STRINGS.get(lg, {}).get(key)
    if s is None:
        s = STRINGS.get(DEFAULT, {}).get(key, key)
    if fmt:
        try:
            return s.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return s
    return s
