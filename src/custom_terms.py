"""Términos de spam que el admin añade desde Telegram, sin tocar el servidor.

El problema que resuelve: las listas negras de `config/blacklist/` son regex y
se editan por SSH. Quien modera desde el móvil ve un anuncio en su grupo y no
puede hacer nada con él hasta llegar a casa. Pero abrir la puerta a escribir
regex desde el chat es peligroso: un `.*` de más y el bot empieza a banear
vecinos, y en este proyecto un falso positivo es peor que un falso negativo.

De ahí las tres decisiones de diseño:

1. **Archivo aparte.** `config/blacklist/custom/<lista>.txt`, fuera de git. Un
   `git pull` no puede pisar el trabajo del admin ni provocar un conflicto.
   Se acumula sobre la lista genérica y las de idioma (ver `wordlists`).

2. **Literales, jamás regex.** El escapado con `re.escape()` ocurre al CARGAR
   (en `wordlists.load_terms`), no al guardar. Guardar el texto en crudo tiene
   dos ventajas: el admin ve en el listado exactamente lo que escribió, y la
   garantía "aquí no entra un regex" se mantiene aunque alguien edite el
   archivo a mano con un editor. Si se guardara ya escapado, bastaría con
   escribir `.*` a mano en el archivo para colar un comodín activo.

3. **Vista previa obligatoria antes de guardar.** `preview_term` dice cuántos
   mensajes REALES y recientes del grupo cazaría el término. Es la diferencia
   entre añadir "oferta" a ciegas y ver que arrasaría con 14 conversaciones
   normales.

La caché de patrones compilados se invalida sola: `wordlists.load_and_compile`
mete la fecha de modificación del archivo en su clave, y además aquí se llama a
`clear_cache()` en cada alta y baja. Sin eso, el admin añadiría un término, no
pasaría nada, y pensaría que el bot no le hace caso.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import wordlists

log = logging.getLogger(__name__)

# Listas gestionables desde Telegram. Es una lista blanca cerrada a propósito:
# el nombre del archivo llega desde un callback de Telegram, y sin esto un
# `../../` viajaría hasta donde quisiera quien lo mandara.
#
# `classifier_excluded_tokens.txt` NO está: va al revés que las demás (son
# palabras que el clasificador IGNORA, no que caza) y no se compila como regex,
# así que el escapado no le aplica.
MANAGEABLE_LISTS: tuple[str, ...] = (
    "bio_cta.txt",
    "bio_illegal_services.txt",
    "bio_spam_keywords.txt",
    "commercial_cta.txt",
    "commercial_domestic.txt",
    "commercial_illegal_services.txt",
    "commercial_money.txt",
    "commercial_money_periodic.txt",
    "commercial_urgency.txt",
    "commercial_work.txt",
)

# Listas que los detectores compilan SIN envolver en \b(?:...)\b, porque sus
# patrones necesitan empezar por símbolo ($500, /day). Ver commercial_ad.py.
NO_BOUNDARIES_LISTS: frozenset[str] = frozenset(
    {"commercial_money.txt", "commercial_money_periodic.txt"},
)

# Un término de 2 o 3 letras casa con media conversación ("pago", "web", "ya").
MIN_TERM_LEN = 4
MAX_TERM_LEN = 120
# Tope por lista: cada término es una rama más de la alternancia que se ejecuta
# en CADA mensaje. Además, quien necesita 300 términos necesita otra cosa.
MAX_TERMS_PER_LIST = 300

# Cuántos mensajes examina la vista previa. Se ejecuta con el admin esperando
# en el chat, así que no puede recorrer la base entera.
PREVIEW_SCAN_LIMIT = 300
PREVIEW_MAX_EXAMPLES = 5

# Códigos de resultado. Se devuelven en crudo (no traducidos) a propósito: el
# panel es quien los pasa por i18n.
OK = "ok"
ERR_UNKNOWN_LIST = "lista_desconocida"
ERR_EMPTY = "vacio"
ERR_TOO_SHORT = "corto"
ERR_TOO_LONG = "largo"
ERR_NO_TEXT = "sin_texto"
ERR_SYMBOL_EDGES = "bordes_simbolo"
ERR_DUPLICATE = "duplicado"
ERR_ALREADY_COVERED = "ya_cubierto"
ERR_LIST_FULL = "lista_llena"
ERR_NOT_FOUND = "no_encontrado"
ERR_IO = "error_escritura"


@dataclass(frozen=True)
class TermResult:
    """Resultado de validar, añadir o quitar. `code` lo traduce el panel."""

    ok: bool
    code: str
    term: str = ""


@dataclass(frozen=True)
class PreviewResult:
    """Lo que cazaría un término candidato entre los mensajes recientes reales."""

    term: str
    valid: TermResult
    scanned: int = 0
    matches: int = 0
    ham_hits: int = 0
    examples: tuple[str, ...] = field(default_factory=tuple)

    @property
    def risky(self) -> bool:
        """Señal para el panel: pinta que este término se lleva por delante gente.

        Cazar un mensaje marcado como legítimo con /legal es la peor señal
        posible: es un falso positivo confirmado por el propio admin.
        """
        return self.ham_hits > 0 or self.matches > 0


# ---------- helpers ----------

def is_manageable(filename: str) -> bool:
    return filename in MANAGEABLE_LISTS


def _uses_boundaries(filename: str) -> bool:
    return filename not in NO_BOUNDARIES_LISTS


def custom_path(filename: str) -> Path:
    """Ruta del archivo personalizado de esa lista (puede no existir aún)."""
    return wordlists.custom_file(filename)


def normalize(term: str) -> str:
    """Limpia el término tal y como se guardará: sin sobras de copiar y pegar.

    Colapsa los espacios repetidos y quita saltos de línea, que romperían el
    formato "un término por línea" del archivo.
    """
    return " ".join(str(term or "").split())


def compile_literal(term: str, *, filename: str | None = None) -> re.Pattern:
    """Compila un término LITERAL igual que lo hará el detector que lo use.

    Escapa y respeta el envoltorio `\\b(?:...)\\b` de la lista de destino, para
    que la vista previa no mienta: lo que aquí casa es lo que casará de verdad.
    """
    boundaries = _uses_boundaries(filename) if filename else True
    return wordlists.compile_alternation(
        [re.escape(term)], boundaries=boundaries, flags=re.IGNORECASE,
    )


# ---------- lectura ----------

def list_terms(filename: str) -> list[str]:
    """Términos personalizados de esa lista, en crudo y en orden de alta."""
    if not is_manageable(filename):
        return []
    return wordlists.read_custom_terms(filename)


def count_terms(filename: str) -> int:
    return len(list_terms(filename))


# ---------- validación ----------

def validate_term(filename: str, term: str) -> TermResult:
    """Comprueba que el término se puede añadir. No escribe nada.

    El orden importa: primero lo barato (longitud, contenido), después lo que
    toca disco o compila patrones.
    """
    if not is_manageable(filename):
        return TermResult(False, ERR_UNKNOWN_LIST)

    clean = normalize(term)
    if not clean:
        return TermResult(False, ERR_EMPTY)
    if len(clean) < MIN_TERM_LEN:
        return TermResult(False, ERR_TOO_SHORT, clean)
    if len(clean) > MAX_TERM_LEN:
        return TermResult(False, ERR_TOO_LONG, clean)

    # "!!!!", "-----", "€€€": sin letras ni números no es un término, y además
    # dispararía en cualquier mensaje con signos de puntuación.
    if sum(ch.isalnum() for ch in clean) < 2:
        return TermResult(False, ERR_NO_TEXT, clean)

    # Las listas con \b(?:...)\b nunca casan un patrón que empiece o acabe en
    # símbolo: \b exige un carácter de palabra al lado. Se rechaza en vez de
    # guardarlo, porque quedaría muerto en silencio y el admin creería estar
    # protegido. (Las listas de importes no llevan ese envoltorio: ahí vale.)
    if _uses_boundaries(filename) and not (clean[0].isalnum() and clean[-1].isalnum()):
        return TermResult(False, ERR_SYMBOL_EDGES, clean)

    existing = list_terms(filename)
    if any(clean.casefold() == t.casefold() for t in existing):
        return TermResult(False, ERR_DUPLICATE, clean)
    if len(existing) >= MAX_TERMS_PER_LIST:
        return TermResult(False, ERR_LIST_FULL, clean)

    # Si las listas del repo ya lo cazan, añadirlo solo engorda la alternancia.
    if _already_covered(filename, clean):
        return TermResult(False, ERR_ALREADY_COVERED, clean)

    return TermResult(True, OK, clean)


def _already_covered(filename: str, term: str) -> bool:
    """¿Los patrones que ya hay cazan este término? Ante la duda, False."""
    try:
        rx = wordlists.load_and_compile(
            filename, [], boundaries=_uses_boundaries(filename),
        )
    except re.error:  # pragma: no cover - compile_alternation ya tolera errores
        return False
    return bool(rx.search(term))


# ---------- escritura ----------

def _write_terms(filename: str, terms: list[str]) -> bool:
    """Reescribe el archivo entero de forma atómica. True si salió bien.

    Atómica (archivo temporal + `os.replace`) porque el bot está sirviendo: un
    corte a media escritura dejaría la lista truncada y el detector cargaría
    media protección sin avisar de nada.
    """
    path = custom_path(filename)
    body = "".join(f"{t}\n" for t in terms)
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("No se pudo guardar la lista personalizada %s: %s", filename, exc)
        tmp.unlink(missing_ok=True)
        return False
    # La caché guarda los patrones ya compilados: sin esto el cambio no tendría
    # efecto hasta reiniciar el bot.
    wordlists.clear_cache()
    return True


def add_term(filename: str, term: str) -> TermResult:
    """Añade un término literal a la lista. Valida antes de escribir."""
    result = validate_term(filename, term)
    if not result.ok:
        return result
    if not _write_terms(filename, [*list_terms(filename), result.term]):
        return TermResult(False, ERR_IO, result.term)
    log.info("Término personalizado añadido a %s: %r", filename, result.term)
    return result


def remove_term(filename: str, term: str) -> TermResult:
    """Quita un término de la lista (comparando sin distinguir mayúsculas)."""
    if not is_manageable(filename):
        return TermResult(False, ERR_UNKNOWN_LIST)
    clean = normalize(term)
    terms = list_terms(filename)
    kept = [t for t in terms if t.casefold() != clean.casefold()]
    if len(kept) == len(terms):
        return TermResult(False, ERR_NOT_FOUND, clean)
    if not _write_terms(filename, kept):
        return TermResult(False, ERR_IO, clean)
    log.info("Término personalizado eliminado de %s: %r", filename, clean)
    return TermResult(True, OK, clean)


# ---------- vista previa ----------

def preview_term(
    db: Any,
    filename: str,
    term: str,
    *,
    chat_id: int | None = None,
    scan_limit: int = PREVIEW_SCAN_LIMIT,
    max_examples: int = PREVIEW_MAX_EXAMPLES,
) -> PreviewResult:
    """Cuántos mensajes recientes REALES cazaría el término, antes de guardarlo.

    Es la red de seguridad del sistema: enseña al admin que su "oferta" pillaría
    a 12 vecinos legítimos ANTES de que empiece a banearlos.

    Mira dos fuentes, las dos acotadas para que salga barato:
      - el último mensaje conocido de cada usuario (`seen_users`), que es
        conversación normal del grupo;
      - las muestras marcadas como legítimas con `/legal`, donde una
        coincidencia es un falso positivo confirmado por el propio admin.

    Un término inválido no se busca: se devuelve con `valid.ok` en False y los
    contadores a cero.
    """
    valid = validate_term(filename, term)
    clean = valid.term or normalize(term)
    # Un duplicado o un término ya cubierto no se puede añadir, pero enseñar lo
    # que casaría sigue siendo útil; vacío o ilegible no hay nada que buscar.
    if not clean or valid.code in (ERR_EMPTY, ERR_NO_TEXT, ERR_UNKNOWN_LIST):
        return PreviewResult(term=clean, valid=valid)

    rx = compile_literal(clean, filename=filename)

    scanned = 0
    matches = 0
    examples: list[str] = []
    for row in _safe_rows(db, "recent_message_texts", chat_id=chat_id, limit=scan_limit):
        text = row["last_msg_text"] if "last_msg_text" in row.keys() else None
        if not text:
            continue
        scanned += 1
        if rx.search(text):
            matches += 1
            if len(examples) < max_examples:
                examples.append(_snippet(text))

    ham_hits = sum(
        1 for text in _safe_ham(db, scan_limit) if text and rx.search(text)
    )

    return PreviewResult(
        term=clean,
        valid=valid,
        scanned=scanned,
        matches=matches,
        ham_hits=ham_hits,
        examples=tuple(examples),
    )


def _safe_rows(db: Any, method: str, **kwargs) -> list:
    """La vista previa es informativa: si la consulta falla, no rompe el panel."""
    try:
        return getattr(db, method)(**kwargs) or []
    except Exception as exc:  # noqa: BLE001 - nunca debe tumbar el panel
        log.warning("Vista previa: falló %s (%s)", method, exc)
        return []


def _safe_ham(db: Any, limit: int) -> list[str]:
    try:
        return db.recent_sample_texts("ham", limit=limit) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("Vista previa: no se pudieron leer las muestras legítimas (%s)", exc)
        return []


def _snippet(text: str, width: int = 120) -> str:
    """Una línea corta del mensaje, para enseñarla en el chat sin inundarlo."""
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= width else f"{one_line[:width - 1]}…"
