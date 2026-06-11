"""Heurística rápida de detección de idioma (sin dependencias externas).

`likely_spanish(text)` devuelve True si parece español por:
  - Presencia de marcadores fuertes: ñ, acentos (áéíóúü), signos invertidos ¿¡
  - O al menos 1 stopword común
  - O ratio stopwords/total_palabras >= 0.15

NO es un detector de idioma preciso; es un guard mínimo para distinguir
"texto que probablemente sea español" vs "texto sospechoso para nuestros
grupos hispanos".

Para algo más preciso usar `lingua-language-detector` (~100MB de modelos),
no usado en este bot por peso.
"""
from __future__ import annotations

import re

_SPANISH_STOPWORDS = frozenset({
    # Determinantes / preposiciones
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "y", "o", "ni", "que", "pero", "porque",
    "como", "donde", "cuando", "porqué", "por", "para", "con", "sin",
    "en", "entre", "hacia", "sobre", "tras", "según", "hasta", "desde",
    # Verbos comunes
    "es", "son", "está", "están", "estaba", "fue", "será", "ha", "han",
    "hay", "haber", "tiene", "tengo", "tenía", "tener", "puede", "pueden",
    "podría", "ser", "estar", "fue", "hizo", "hacer",
    # Pronombres
    "yo", "tú", "él", "ella", "nosotros", "vosotros", "ellos", "ellas",
    "me", "te", "le", "lo", "la", "se", "su", "mi", "tu", "nos", "os", "les",
    # Negación / afirmación
    "no", "sí", "tampoco", "también", "ya", "aún", "todavía",
    # Conectores y adverbios
    "muy", "más", "menos", "bien", "mal", "ahora", "aquí", "allí",
    "siempre", "nunca", "casi", "solo", "sólo", "incluso", "además",
    # Saludos / cortesía
    "hola", "buenos", "buenas", "días", "tardes", "noches", "adiós",
    "gracias", "favor", "perdón", "saludos",
    # Pronombres demostrativos / indefinidos
    "esto", "eso", "aquello", "esta", "este", "estas", "estos",
    "algo", "alguien", "alguno", "alguna", "algún", "nada", "nadie",
    # Verbos auxiliares modales
    "quiero", "quieres", "quiere", "necesito", "necesita", "puedo",
    "podemos", "debemos", "vamos", "vais", "van",
    # Muletillas y comunes en charla
    "vale", "venga", "pues", "tal", "qué", "cuál", "quién",
    "alguien", "ayuda", "sabe", "sabéis", "veo", "creo", "pienso",
})

_ACCENT_RE = re.compile(r"[ñÑáéíóúüÁÉÍÓÚÜ¿¡]")
_WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)


def likely_spanish(text: str | None, min_chars: int = 5) -> bool:
    """Heurística rápida de español. Devuelve True si parece español.

    Si el texto es muy corto (< min_chars), devuelve False (no podemos saber).
    """
    if not text or len(text.strip()) < min_chars:
        return False
    # Marcadores fuertes
    if _ACCENT_RE.search(text):
        return True
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return False
    matches = sum(1 for w in words if w in _SPANISH_STOPWORDS)
    if matches == 0:
        return False
    return matches >= 1 or (matches / len(words)) >= 0.15
