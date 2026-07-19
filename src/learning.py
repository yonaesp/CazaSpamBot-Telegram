"""Sistema de aprendizaje activo.

El admin entrena al bot con `/spam` (reply) y `/ham` (reply). Los textos
normalizados se guardan en SQLite y un detector posterior los compara con
mensajes nuevos usando char-ngram similarity (sin sklearn — implementación
mínima en stdlib).
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import unicodedata
from collections import Counter
from typing import Iterable

from .wordlists import active_langs, load_terms

log = logging.getLogger(__name__)

_ZW = re.compile(r"[​-‍⁠﻿᠎]")


def normalize(text: str | None) -> str:
    """Normalización compartida: NFKC + strip zero-width + casefold."""
    if not text:
        return ""
    t = _ZW.sub("", text)
    t = unicodedata.normalize("NFKC", t)
    return t.casefold().strip()


def text_hash(text_norm: str) -> str:
    return hashlib.blake2b(text_norm.encode("utf-8"), digest_size=8).hexdigest()


# ----------------- Tabla SQL -----------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS learning_samples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text_norm     TEXT NOT NULL,
    text_hash     TEXT NOT NULL,
    label         TEXT NOT NULL CHECK (label IN ('spam','ham')),
    added_by      INTEGER NOT NULL,
    chat_id       INTEGER,
    source_user   INTEGER,
    ts            REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_samples_hash_label ON learning_samples(text_hash, label);
CREATE INDEX IF NOT EXISTS idx_samples_label_ts ON learning_samples(label, ts DESC);
"""


# ----------------- char-ngrams + cosine similarity -----------------


def _char_ngrams(text: str, n_min: int = 3, n_max: int = 5) -> Counter:
    """Cuenta char-ngrams de [n_min, n_max]. Marca límites de palabra con espacios."""
    t = f" {text} "
    grams: Counter = Counter()
    for n in range(n_min, n_max + 1):
        for i in range(len(t) - n + 1):
            grams[t[i:i + n]] += 1
    return grams


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    inter = set(a) & set(b)
    if not inter:
        return 0.0
    dot = sum(a[k] * b[k] for k in inter)
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def best_match(query_text: str, samples: Iterable[str]) -> tuple[float, str | None]:
    """Devuelve (similarity_max, sample_match) contra una lista de samples."""
    if not query_text or len(query_text) < 10:
        return 0.0, None
    q_grams = _char_ngrams(query_text)
    best_sim = 0.0
    best_sample = None
    for s in samples:
        if not s or len(s) < 10:
            continue
        sim = _cosine(q_grams, _char_ngrams(s))
        if sim > best_sim:
            best_sim = sim
            best_sample = s
    return best_sim, best_sample


# ----------------- Naive Bayes -----------------

_WORD_RE = re.compile(r"\w{2,}", re.UNICODE)

# Mínimo de samples por clase para que Bayes dé señal fiable.
# Por debajo de esto, devolvemos None (no entrenado lo bastante).
BAYES_MIN_SAMPLES_PER_CLASS = 10

# Tope al peso (log-odds) que puede aportar UN token suelto.
#
# Sin tope, una palabra que sale en 10 muestras de spam y en ninguna de ham
# decide ella sola el veredicto del mensaje. Eso es venenoso en cuanto el
# vocabulario del grupo se cuela en las muestras: en un grupo de fotografía
# basta con que varios spammers vendan cámaras para que "cámara" pase a ser
# señal de spam, y quien pregunte por la suya se lleve un mute. Con tope hacen
# falta VARIAS palabras sospechosas para superar el umbral, que es justo lo que
# distingue un anuncio de una pregunta normal.
BAYES_MAX_TOKEN_LOGRATIO = 1.1  # ~3:1 de odds por token

# Un token que aparece en las DOS clases no separa nada: pesa la mitad.
BAYES_SHARED_TOKEN_FACTOR = 0.5

# Un token visto UNA sola vez en todo el corpus es ruido, no evidencia: pudo
# entrar de rebote en una única muestra. No se descarta (con corpus pequeños
# casi todo es hapax y el clasificador se quedaría mudo), pero pesa un tercio.
BAYES_RARE_TOKEN_FACTOR = 0.34
BAYES_RARE_TOKEN_MAX_FREQ = 1


# Tokens NEUTROS: no distinguen spam de ham y solo ensucian el clasificador.
# Se eliminan antes de contar para el Bayes. Dos fuentes:
#   - palabras funcionales del idioma (en código, abajo): valen para cualquier
#     comunidad, sea de cocina, fotografía o domótica.
#   - vocabulario temático de TU grupo, editable en
#     config/blacklist/classifier_excluded_tokens.txt (una palabra por línea).
#     Ahí NO hay defaults en código a propósito: el vocabulario de un grupo solo
#     lo conoce su admin, y meter el de otra comunidad no ayuda a nadie.
_STOPWORDS_ES = frozenset({
    "que", "de", "la", "el", "en", "los", "las", "un", "una", "para", "por",
    "con", "no", "se", "su", "es", "lo", "le", "me", "mi", "te", "tu", "al",
    "del", "como", "mas", "más", "pero", "si", "ya", "muy", "este", "esta",
    "eso", "esto", "hay", "ser", "soy", "son", "tiene", "tengo", "todo",
    "bien", "hola", "gracias", "buenas", "buenos", "dias", "días",
    "yo", "he", "ha", "han", "hace", "hacer", "sabe", "saber", "puede",
    "poder", "quiero", "alguien", "algo", "nada", "cuando", "donde", "dónde",
    "porque", "sobre", "desde", "hasta", "sin", "tambien", "también", "solo",
    "sólo", "cual", "cuál", "quien", "quién", "otro", "otra", "aqui", "aquí",
    "ahora", "siempre", "nunca", "asi", "así", "vez", "cosa", "favor",
})
_STOPWORDS_EN = frozenset({
    "the", "and", "for", "you", "your", "with", "this", "that", "have", "has",
    "are", "was", "were", "not", "but", "can", "could", "would", "should",
    "from", "there", "here", "what", "when", "where", "who", "how", "why",
    "all", "any", "some", "one", "two", "get", "got", "just", "like", "know",
    "think", "want", "need", "make", "does", "did", "doing", "than", "then",
    "them", "they", "their", "its", "it's", "about", "out", "into", "over",
    "hello", "thanks", "thank", "please", "yes", "sorry",
})
# Sin defaults temáticos en código: si el archivo no existe, no se excluye nada
# más allá de las palabras funcionales. Ver config/blacklist/README.md.
_DEFAULT_THEMATIC_TOKENS: list[str] = []
_EXCLUDED_CACHE: dict[tuple[str, ...], frozenset[str]] = {}


def _excluded_tokens() -> frozenset[str]:
    """Tokens neutros del idioma activo (se lee tarde: al importar este módulo
    el bot todavía no ha resuelto su idioma)."""
    key = tuple(active_langs())
    cached = _EXCLUDED_CACHE.get(key)
    if cached is None:
        cached = _STOPWORDS_ES | _STOPWORDS_EN | frozenset(
            t.lower()
            for t in load_terms("classifier_excluded_tokens.txt", _DEFAULT_THEMATIC_TOKENS)
        )
        _EXCLUDED_CACHE[key] = cached
    return cached


def _tokenize(text: str) -> list[str]:
    """Tokeniza texto en palabras (mín 2 chars), eliminando tokens neutros que
    no aportan señal al clasificador (stop-words + vocabulario temático)."""
    excluded = _excluded_tokens()
    return [t for t in _WORD_RE.findall(text) if t.lower() not in excluded]


def naive_bayes_spam_prob(
    text: str, spam_samples: list[str], ham_samples: list[str],
) -> float | None:
    """Probabilidad 0..1 de que el texto sea spam según Naive Bayes Multinomial
    con Laplace smoothing y softmax. None si no hay suficientes samples.
    """
    if (
        len(spam_samples) < BAYES_MIN_SAMPLES_PER_CLASS
        or len(ham_samples) < BAYES_MIN_SAMPLES_PER_CLASS
    ):
        return None

    spam_counts: Counter = Counter()
    ham_counts: Counter = Counter()
    for s in spam_samples:
        spam_counts.update(_tokenize(s))
    for h in ham_samples:
        ham_counts.update(_tokenize(h))
    total_spam = sum(spam_counts.values())
    total_ham = sum(ham_counts.values())
    if total_spam == 0 or total_ham == 0:
        return None

    n_spam = len(spam_samples)
    n_ham = len(ham_samples)
    prior_spam = n_spam / (n_spam + n_ham)

    vocab = set(spam_counts) | set(ham_counts)
    V = len(vocab)

    tokens = _tokenize(text)
    if not tokens:
        return None

    # Trabajamos con log-odds (log P(spam) - log P(ham)) en vez de acumular las
    # dos probabilidades por separado: es lo mismo (el softmax de dos clases solo
    # depende de la diferencia) y permite topar la aportación de cada token.
    log_odds = math.log(prior_spam) - math.log(1 - prior_spam)

    for tok in tokens:
        # Laplace smoothing
        n_tok_spam = spam_counts.get(tok, 0)
        n_tok_ham = ham_counts.get(tok, 0)
        p_t_given_spam = (n_tok_spam + 1) / (total_spam + V)
        p_t_given_ham = (n_tok_ham + 1) / (total_ham + V)
        weight = math.log(p_t_given_spam) - math.log(p_t_given_ham)

        if weight <= 0:
            # Evidencia que EXCULPA (el token tira hacia ham): pasa entera.
            # El tope es asimétrico a propósito, por la regla número uno del
            # proyecto: mejor dejar pasar spam que castigar a un legítimo. Para
            # acusar exigimos varias señales; para absolver, con una basta.
            log_odds += weight
            continue
        cap = BAYES_MAX_TOKEN_LOGRATIO
        if n_tok_ham:
            # Sale en spam Y en ham: no distingue, pesa la mitad.
            cap *= BAYES_SHARED_TOKEN_FACTOR
        elif n_tok_spam + n_tok_ham <= BAYES_RARE_TOKEN_MAX_FREQ:
            # Visto una sola vez en todo el corpus: ruido, no evidencia.
            cap *= BAYES_RARE_TOKEN_FACTOR
        log_odds += min(cap, weight)

    return _sigmoid(log_odds)


def _sigmoid(x: float) -> float:
    """Logística estable: la rama negativa evita el overflow de exp(-x)."""
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    e = math.exp(x)
    return e / (1 + e)


# ----------------- Detector combinado -----------------

# Longitud mínima para fiarse de una similitud MEDIA (0.6-0.8).
#
# El coseno de char-ngrams se infla en textos cortos: comparten pocos ngramas en
# total, así que unos pocos en común disparan el porcentaje. Medido con una sola
# muestra de spam ("hola busco gente para trabajar desde casa escribeme"), el
# mensaje inocente "hola busco gente para jugar escribeme" daba 0.67 y se llevaba
# un mute. Por debajo de este umbral exigimos similitud ALTA (>0.8), que ya es
# prácticamente calcar el mensaje.
COSINE_MEDIUM_MIN_CHARS = 40


def check_against_samples(
    text: str | None,
    spam_samples: list[str],
    ham_samples: list[str],
) -> tuple[int, str | None]:
    """Combina Cosine similarity (caso por caso) + Naive Bayes (probabilidad global).

    Resultados:
      - Cosine high (>0.8) Y Bayes high (>0.8) → 100 (ban casi seguro)
      - Cosine high (>0.8)                     → 80
      - Cosine medio (>0.6), texto largo       → 60
      - Bayes high (>0.85)                     → 50 (señal estadística)
      - Cosine ham high (>0.5) o Bayes ham (<0.2) → -30/-20 (cancela score)

    Devuelve (score, sample_match). sample_match es el texto del spam
    similar (si lo hay) o "bayes" si la señal viene del clasificador.
    """
    norm_text = normalize(text)
    if not norm_text:
        return 0, None
    spam_sim, spam_match = best_match(norm_text, spam_samples)
    ham_sim, _ = best_match(norm_text, ham_samples)
    p_spam = naive_bayes_spam_prob(norm_text, spam_samples, ham_samples)

    # Combinación: cosine + bayes
    if spam_sim > 0.8 and p_spam is not None and p_spam > 0.8:
        return 100, spam_match
    if spam_sim > 0.8:
        return 80, spam_match
    if spam_sim > 0.6 and len(norm_text) >= COSINE_MEDIUM_MIN_CHARS:
        return 60, spam_match
    if p_spam is not None and p_spam > 0.85:
        return 50, "bayes"
    # Señal HAM (cancela score si alguien comparte vocabulario con un sample previo legítimo)
    if ham_sim > 0.5:
        return -30, None
    if p_spam is not None and p_spam < 0.2:
        return -20, None
    return 0, None
