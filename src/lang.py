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

# Inglés: sin marcas ortográficas propias, así que solo cuentan las stopwords.
_ENGLISH_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "because", "as", "if", "of", "to",
    "in", "on", "at", "for", "with", "without", "from", "by", "about", "into",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "can", "could", "will", "would", "should", "may",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their", "this", "that", "these", "those",
    "not", "no", "yes", "too", "also", "very", "more", "less", "well", "now",
    "here", "there", "always", "never", "just", "only", "even", "still",
    "hello", "hi", "thanks", "thank", "please", "sorry", "good", "morning",
    "what", "which", "who", "how", "when", "where", "why", "help", "know",
    "need", "want", "think", "see", "get", "make", "use", "try", "any", "some",
})

_ACCENT_RE = re.compile(r"[ñÑáéíóúüÁÉÍÓÚÜ¿¡]")
_WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)


def _parece(text: str | None, palabras: frozenset, marcas, min_chars: int) -> bool:
    """La heurística, sin atarla a ningún idioma concreto.

    `marcas` es un regex de signos que solo usa ese idioma (la ñ y los acentos en
    español, nada en inglés) o None si no los tiene.
    """
    if not text or len(text.strip()) < min_chars:
        return False
    if marcas is not None and marcas.search(text):
        return True
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return False
    matches = sum(1 for w in words if w in palabras)
    if matches == 0:
        return False
    return matches >= 1 or (matches / len(words)) >= 0.15


def likely_spanish(text: str | None, min_chars: int = 5) -> bool:
    """Heurística rápida de español. Devuelve True si parece español.

    Si el texto es muy corto (< min_chars), devuelve False (no podemos saber).
    """
    return _parece(text, _SPANISH_STOPWORDS, _ACCENT_RE, min_chars)


# Idiomas con lista de palabras corrientes. Cuál se usa lo decide el idioma
# ACTIVO del bot, no el código: `external_mention` puntúa 130 en vez de 60 cuando
# el texto que acompaña a una mención «no parece del idioma del grupo», y con la
# heurística clavada al español ese salto se le aplicaba a CUALQUIER instalación.
# Un grupo inglés se comía la puntuación máxima por escribir en inglés.
_POR_IDIOMA = {
    "es": (_SPANISH_STOPWORDS, _ACCENT_RE),
    "en": (_ENGLISH_STOPWORDS, None),
}


def parece_del_idioma_activo(text: str | None, min_chars: int = 5) -> bool:
    """¿El texto parece escrito en el idioma configurado en el bot?

    Con un idioma del que no tenemos vocabulario devuelve **True**: «no lo sé» no
    puede castigar a nadie. Es la diferencia entre no saber y acusar, y aquí el
    resultado se usa para subir la puntuación de 60 a 130.
    """
    from .i18n import current_lang
    datos = _POR_IDIOMA.get(current_lang())
    if datos is None:
        return True
    palabras, marcas = datos
    return _parece(text, palabras, marcas, min_chars)
