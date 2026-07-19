"""Carga de listas negras editables desde `config/blacklist/`.

Cada archivo es texto plano: un patrón por línea (palabra suelta o regex),
líneas vacías y las que empiezan por `#` se ignoran. Así cualquiera puede
personalizar las palabras/frases que disparan el antispam SIN tocar código.

Si el archivo no existe, se usan los `defaults` pasados (fallback en el código),
de modo que el bot funciona out-of-the-box aunque falte `config/`.

## Listas por idioma (acumulativas)

Además del archivo genérico `config/blacklist/<archivo>`, se leen las variantes
por idioma `config/blacklist/<lang>/<archivo>`. Los patrones se SUMAN (sin
duplicados): el spam llega en cualquier idioma, así que un grupo español debe
poder cazar también el spam en inglés.

Qué idiomas se cargan: el idioma activo del bot MÁS inglés (lengua franca del
spam en Telegram). Se puede forzar otro conjunto con `BLACKLIST_LANGS=es,en,pt`.

Una instalación sin subdirectorios se comporta EXACTAMENTE igual que antes.

## Patrones inválidos

Los patrones los escribe el usuario a mano. Uno mal formado NO puede tumbar el
bot (antes reventaba el import del detector y el bot ni arrancaba): se descarta
ese patrón, se avisa en el log y el resto siguen protegiendo.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from .i18n import current_lang

log = logging.getLogger(__name__)

_BLACKLIST_DIR = Path(__file__).resolve().parent.parent / "config" / "blacklist"

# Inglés siempre: es la lengua franca del spam en Telegram (ofertas de trabajo
# falsas, cripto, "recovery experts"), llegue al grupo que llegue.
_LINGUA_FRANCA = "en"

_NEVER_MATCHES = r"(?!x)x"  # patrón imposible: no casa nunca

# Cache de patrones ya compilados. La clave incluye el directorio y el idioma
# activo para que un cambio de idioma en caliente (/idioma) recargue las listas
# y para que los tests que monkeypatchean `_BLACKLIST_DIR` no se contaminen.
_COMPILED: dict[tuple, re.Pattern] = {}


def active_langs() -> list[str]:
    """Idiomas cuyas listas negras se cargan, en orden y sin duplicados.

    Por defecto: idioma activo del bot + inglés. `BLACKLIST_LANGS` (CSV) lo
    sustituye por completo, para quien modere una comunidad multilingüe y
    quiera cargar también, p.ej., portugués.
    """
    override = (os.getenv("BLACKLIST_LANGS") or "").strip()
    if override:
        wanted = [c.strip().lower()[:2] for c in override.split(",")]
    else:
        wanted = [current_lang(), _LINGUA_FRANCA]
    out: list[str] = []
    for code in wanted:
        if code and code.isalpha() and code not in out:
            out.append(code)
    return out


def clear_cache() -> None:
    """Olvida los patrones compilados (tests y recarga tras cambiar de idioma)."""
    _COMPILED.clear()


def _read_terms_file(path: Path) -> list[str] | None:
    """Términos útiles del archivo, o None si no se puede leer."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return [
        ln.strip() for ln in raw.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]


def load_terms(
    filename: str, defaults: list[str], *, langs: list[str] | None = None,
) -> list[str]:
    """Términos de config/blacklist/<filename> MÁS los de <lang>/<filename>.

    La base es el archivo genérico (o `defaults` si no existe o está vacío),
    igual que siempre. Encima se acumulan las listas de los idiomas activos,
    sin duplicados (comparando sin distinguir mayúsculas).
    """
    terms = _read_terms_file(_BLACKLIST_DIR / filename) or list(defaults)
    seen = {term.casefold() for term in terms}
    for lang in (active_langs() if langs is None else langs):
        for term in _read_terms_file(_BLACKLIST_DIR / lang / filename) or []:
            if term.casefold() not in seen:
                seen.add(term.casefold())
                terms.append(term)
    return terms


def _wrap(body: str, *, boundaries: bool) -> str:
    return rf"\b(?:{body})\b" if boundaries else rf"(?:{body})"


def _valid_terms(terms: list[str], flags: int) -> list[str]:
    """Descarta los patrones que ni siquiera compilan por separado."""
    ok: list[str] = []
    for term in terms:
        if not term:
            continue
        try:
            re.compile(term, flags)
        except re.error as exc:
            log.warning("Patrón de lista negra inválido, se ignora: %r (%s)", term, exc)
            continue
        ok.append(term)
    return ok


def compile_alternation(
    terms: list[str], *, boundaries: bool = True, flags: int = re.IGNORECASE,
) -> re.Pattern:
    """Compila los términos en una alternancia de regex `(?:a|b|c)`.

    Cada término es una alternativa de regex (NO se escapa: se admiten regex).
    Para evitar romper el conteo de coincidencias, usa grupos NO capturantes
    `(?:...)` dentro de tus términos, nunca `(...)`.

    boundaries=True envuelve en `\\b(?:...)\\b` (palabra completa).

    Los patrones que no compilan se descartan con un aviso en el log: una lista
    mal editada degrada la detección, nunca impide arrancar el bot.
    """
    terms = _valid_terms(terms, flags)
    try:
        return re.compile(_wrap("|".join(terms) or _NEVER_MATCHES, boundaries=boundaries), flags)
    except re.error as exc:
        # Cada patrón compila suelto pero juntos no (p.ej. una referencia \1 que
        # apunta a un grupo de otro término). Se reconstruye de uno en uno y se
        # deja fuera al que rompe la alternancia.
        log.warning("La alternancia de patrones no compila (%s); se reconstruye", exc)
        safe: list[str] = []
        for term in terms:
            try:
                re.compile(_wrap("|".join([*safe, term]), boundaries=boundaries), flags)
            except re.error:
                log.warning("Patrón descartado por romper la alternancia: %r", term)
                continue
            safe.append(term)
        return re.compile(_wrap("|".join(safe) or _NEVER_MATCHES, boundaries=boundaries), flags)


def load_and_compile(
    filename: str, defaults: list[str], *, boundaries: bool = True, flags: int = re.IGNORECASE,
) -> re.Pattern:
    """Atajo: carga los términos del archivo (+ idiomas activos) y los compila.

    El resultado se cachea por (archivo, directorio, idiomas), así que llamarlo
    en cada mensaje sale gratis y a la vez respeta un cambio de idioma.
    """
    key = (filename, str(_BLACKLIST_DIR), boundaries, flags, tuple(active_langs()))
    rx = _COMPILED.get(key)
    if rx is None:
        rx = compile_alternation(
            load_terms(filename, defaults), boundaries=boundaries, flags=flags,
        )
        _COMPILED[key] = rx
    return rx
