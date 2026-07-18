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

from .locales import AVAILABLE, FALLBACK, STRINGS

log = logging.getLogger(__name__)

# Idiomas soportados = archivos de idioma encontrados (autodescubrimiento). Soltar un
# `fr.json` en src/locales/ basta para que /idioma lo acepte: cero cambios de código.
SUPPORTED = AVAILABLE
DEFAULT = FALLBACK
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


def variant_keys(prefix: str, _lang: str | None = None) -> list[str]:
    """Claves de las frases alternativas numeradas `prefix.1`, `prefix.2`, ...

    Los textos que el bot alterna al azar (acuses de recibo a quien reporta,
    agradecimientos...) viven como claves numeradas para que CADA idioma pueda
    tener su propio número de frases: se recorre desde 1 y se para en el primer
    hueco. Se mira el paquete de idioma DIRECTAMENTE, sin el fallback de `t()`:
    si no, un idioma con 3 frases donde el español tiene 9 acabaría colando
    castellano en las 6 restantes.

    Si el idioma no aporta ninguna, se devuelven las del idioma de referencia,
    que `t()` resolverá con su propio fallback. Así la lista NUNCA queda vacía:
    `random.choice([])` lanzaría IndexError y el usuario se quedaría sin mensaje.
    """
    lg = _lang or _current

    def _claves(code: str) -> list[str]:
        pack = STRINGS.get(code, {})
        claves, i = [], 1
        while f"{prefix}.{i}" in pack:
            claves.append(f"{prefix}.{i}")
            i += 1
        return claves

    return _claves(lg) or _claves(DEFAULT)


def t(key: str, _lang: str | None = None, **fmt) -> str:
    """Texto traducido: idioma dado o el global; fallback ES y luego la propia clave.

    El selector de idioma se llama `_lang` (con guion bajo) A PROPÓSITO: así nunca
    colisiona con un placeholder del texto. Con el nombre `lang`, una llamada como
    `t("lang.set", lang=x)` enlazaba x al SELECTOR en vez de a `**fmt`, `.format()`
    no llegaba a ejecutarse y el usuario veía «{lang}» literal (bug real, 2026-07-18).
    """
    lg = (_lang or _current)
    s = STRINGS.get(lg, {}).get(key)
    if s is None:
        s = STRINGS.get(DEFAULT, {}).get(key, key)
    if fmt:
        try:
            return s.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return s
    return s
