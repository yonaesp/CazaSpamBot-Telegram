"""Detector: el enlace lleva a un chat que se anuncia solo como spam.

Compañero de `link_reader`, que es quien va a mirar el destino. Aquí solo se juzga
lo que ese destino dice DE SÍ MISMO: su título y su descripción públicas.

Por qué esto no es «otro detector de palabras»:

- No mira el mensaje del usuario. Mira la ficha del chat enlazado, escrita por
  quien monta el canal para atraer clientes. Nadie describe su canal como «packs
  caseros» sin dedicarse a eso.
- Por eso el listón de falsos positivos es distinto al de un mensaje suelto: en un
  grupo de informática o domótica se habla de dinero, de trabajo y de fotos a
  todas horas, pero NADIE enlaza un canal titulado «Jovencitas / Colegialas».

Se acumulan dos listas, ambas editables:

- `config/blacklist/link_target_keywords.txt` — específica de destinos enlazados.
- `config/blacklist/personal_channel_keywords.txt` — el vocabulario de blanqueo,
  apuestas, documentos falsos y accesos robados que ya se usa para el canal del
  perfil. El criterio es idéntico («lo que ningún chat honesto pone en su título»),
  así que se reutiliza en vez de duplicarlo: un término añadido allí protege aquí.

Nota de compilación: igual que en `personal_channel`, se compila SIN el envoltorio
`\\b(?:...)\\b`, porque el chino y el japonés no separan palabras con espacios y el
`\\b` dejaría muertos todos sus patrones. Los patrones latinos traen sus propios `\\b`.
"""
from __future__ import annotations

from ..i18n import t
from ..wordlists import compile_alternation, load_terms
from . import Hit
from .personal_channel import _DEFAULT_CHANNEL_KEYWORDS

# Alto a propósito: sumado a los 50 del enlace externo pasa de BAN_SCORE. El
# destino confeso es la prueba, no un indicio más.
SCORE = 100

_DEFAULT_LINK_TARGET_KEYWORDS = [
    # --- Venta de contenido sexual (el caso real que originó el detector) ---
    # Los pares van con separador flexible porque estos canales encadenan reclamos
    # con barras: «Mujeres / Packs / Caseros / Videos / Erome / Jovencitas».
    r"\bpacks?\b[\s/|,·+-]{0,3}\b(?:caseros?|exclusivos?|filtrados?|premium)\b",
    r"\b(?:caseros?|exclusivos?|filtrados?)\b[\s/|,·+-]{0,3}\bpacks?\b",
    r"\bpacks?\s+(?:y\s+)?(?:videos?|fotos?)\s+exclusivos?\b",
    r"\b(?:vendo|venta\s+de)\s+packs?\b",
    r"\bjovencitas\b", r"\bcolegialas\b",
    r"\bcontenido\s*\+?\s*18\b", r"\bpack\s+de\s+(?:chicas|nenas|pibas)\b",
    r"\bvideos?\s+porno\b", r"\bporno\s+(?:gratis|amateur|casero)\b",
    r"\bnudes?\s+(?:leaks?|packs?|gratis)\b", r"\bleaks?\s+nudes?\b",
    # --- Reclamo de canal de spam genérico ---
    r"\bcuentas\s+(?:premium|hackeadas)\s+gratis\b",
    r"\btarjetas\s+(?:clonadas|robadas)\b",
]


def _keywords_re():
    terms = load_terms("link_target_keywords.txt", _DEFAULT_LINK_TARGET_KEYWORDS)
    terms += load_terms("personal_channel_keywords.txt", _DEFAULT_CHANNEL_KEYWORDS)
    return compile_alternation(terms, boundaries=False)


def check(destino) -> Hit:
    """Juzga un `link_reader.Destino`. Sin destino legible no dispara."""
    if destino is None:
        return Hit.none()
    texto = getattr(destino, "texto", "") or ""
    if not texto.strip():
        return Hit.none()
    if not _keywords_re().search(texto):
        return Hit.none()
    titulo = (getattr(destino, "titulo", "") or texto)[:80]
    return Hit(
        rule="link_target_spam",
        score=SCORE,
        reason=t("reason.link_target_spam", title=titulo),
        payload={
            "url": getattr(destino, "url", None),
            "title": getattr(destino, "titulo", "")[:200],
            "about": getattr(destino, "descripcion", "")[:200],
        },
    )
