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

## Términos personalizados (`config/blacklist/custom/`)

Encima de todo lo anterior se acumula `config/blacklist/custom/<archivo>`, la
lista que gestiona el propio bot desde Telegram (ver `custom_terms.py`). Va en
una carpeta aparte y fuera de git a propósito: así un `git pull` nunca pisa lo
que ha añadido el admin ni genera conflictos.

Sus líneas son **texto literal, nunca regex**: se escapan con `re.escape()` al
cargarlas. El escapado se hace AQUÍ, al leer, y no al guardar, para que la
garantía valga también si alguien edita el archivo a mano: da igual lo que
escriba, `.*` es un punto y un asterisco, no un comodín.

Sin archivos en `custom/` todo se comporta EXACTAMENTE igual que antes.

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

# Subcarpeta de los términos que añade el admin desde Telegram. Fuera de git.
_CUSTOM_SUBDIR = "custom"

# Tope de líneas que se leen de un archivo personalizado. El límite "de verdad"
# lo aplica `custom_terms.add_term`; este es el cinturón de seguridad por si el
# archivo lo engorda un humano a mano: una lista gigante no puede dejar el bot
# masticando una alternancia de miles de ramas en CADA mensaje.
_CUSTOM_MAX_TERMS = 500

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
    """Términos útiles del archivo, o None si no se puede leer.

    `errors="replace"` no es cosmético: sin él, un archivo guardado en latin-1
    (o con un byte suelto de un copia y pega) lanzaba UnicodeDecodeError, que no
    es OSError, y se llevaba por delante la carga entera del detector. Ahora se
    pierde el carácter ilegible y el resto de la lista sigue protegiendo.
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    return [
        ln.strip() for ln in raw.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]


def custom_file(filename: str) -> Path:
    """Ruta del archivo de términos personalizados de esa lista."""
    return _BLACKLIST_DIR / _CUSTOM_SUBDIR / filename


def read_custom_terms(filename: str) -> list[str]:
    """Términos personalizados en crudo, tal cual los escribió el admin.

    Sin escapar: es lo que se le enseña por pantalla y lo que compara
    `custom_terms` para detectar duplicados. Para MATCHING no se usa nunca esta
    función directamente, sino `load_terms`, que los escapa.
    """
    return (_read_terms_file(custom_file(filename)) or [])[:_CUSTOM_MAX_TERMS]


def _custom_stamp(filename: str) -> tuple:
    """Huella del archivo personalizado, para poder invalidar la caché.

    Si cambia (lo tocó el bot o un humano con un editor), la clave de caché
    cambia con ella y los patrones se recompilan solos. Un `stat()` cuesta
    microsegundos, mucho menos que la propia búsqueda del regex.
    """
    try:
        st = custom_file(filename).stat()
    except OSError:
        return ()
    return (st.st_mtime_ns, st.st_size)


def load_terms(
    filename: str, defaults: list[str], *, langs: list[str] | None = None,
) -> list[str]:
    """Términos de config/blacklist/<filename> MÁS los de <lang>/<filename>.

    La base es el archivo genérico (o `defaults` si no existe o está vacío),
    igual que siempre. Encima se acumulan las listas de los idiomas activos y,
    por último, los términos personalizados de `custom/<filename>`, todos sin
    duplicados (comparando sin distinguir mayúsculas).

    Los personalizados se escapan con `re.escape()`: por esa vía es IMPOSIBLE
    que entre un regex activo, venga del panel de Telegram o de un humano
    editando el archivo a mano.
    """
    terms = _read_terms_file(_BLACKLIST_DIR / filename) or list(defaults)
    seen = {term.casefold() for term in terms}
    for lang in (active_langs() if langs is None else langs):
        for term in _read_terms_file(_BLACKLIST_DIR / lang / filename) or []:
            if term.casefold() not in seen:
                seen.add(term.casefold())
                terms.append(term)
    for raw in read_custom_terms(filename):
        term = re.escape(raw)
        if term.casefold() not in seen:
            seen.add(term.casefold())
            terms.append(term)
    return terms


def _wrap(body: str, *, boundaries: bool) -> str:
    r"""Envuelve la alternancia exigiendo que no quede pegada a otra palabra.

    Se usa `(?<!\w)…(?!\w)` y **no** `\b…\b`, que es lo que había. Para un
    término normal («bet») las dos formas hacen lo mismo: no casan dentro de
    «Roberto». La diferencia aparece cuando una alternativa empieza o acaba en
    algo que NO es carácter de palabra, como los símbolos de moneda:

        \b(?:…|\d+\s*[€$]|[€$]\s*\d+|…)\b

    Ahí `\b` exige una frontera de palabra pegada al símbolo, y esa frontera no
    existe: `$` no es carácter de palabra, así que junto a un espacio o al final
    de la línea no hay transición. Resultado medido el 2026-08-29: **ni `$500`
    ni `500€` casaban**. La señal de dinero de `commercial_ad` llevaba muerta en
    silencio quién sabe cuánto, y el `CLAUDE.md` documentaba lo contrario
    («ambas formas soportadas»), porque los tests usaban importes escritos en
    palabra («500 euros», «500 USD») que sí pasan el `\b`.

    Los lookarounds no exigen transición: solo prohíben que haya letra o dígito
    pegados, que es lo que de verdad se quiere.
    """
    return rf"(?<!\w)(?:{body})(?!\w)" if boundaries else rf"(?:{body})"


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

    El resultado se cachea por (archivo, directorio, idiomas, huella del archivo
    personalizado), así que llamarlo en cada mensaje sale gratis, respeta un
    cambio de idioma y recoge al vuelo un término recién añadido o quitado: sin
    la huella en la clave, el admin añadiría un término y el bot seguiría
    ignorándolo hasta el siguiente reinicio.
    """
    key = (
        filename, str(_BLACKLIST_DIR), boundaries, flags,
        tuple(active_langs()), _custom_stamp(filename),
    )
    rx = _COMPILED.get(key)
    if rx is None:
        rx = compile_alternation(
            load_terms(filename, defaults), boundaries=boundaries, flags=flags,
        )
        # Fuera la versión anterior de esta misma lista: si no, cada edición
        # dejaría para siempre su patrón viejo ocupando memoria.
        for old in [k for k in _COMPILED if k[:5] == key[:5]]:
            del _COMPILED[old]
        _COMPILED[key] = rx
    return rx
