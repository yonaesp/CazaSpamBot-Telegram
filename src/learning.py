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

from .wordlists import load_terms

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


# Tokens NEUTROS: aparecen tanto en spam como en ham y ensucian el clasificador.
# Se eliminan antes de contar para el Bayes. Dos fuentes:
#   - stop-words españolas frecuentes (en código, abajo)
#   - vocabulario temático de TUS grupos, editable en
#     config/blacklist/classifier_excluded_tokens.txt (una palabra por línea)
_STOPWORDS_ES = frozenset({
    "que", "de", "la", "el", "en", "los", "las", "un", "una", "para", "por",
    "con", "no", "se", "su", "es", "lo", "le", "me", "mi", "te", "tu", "al",
    "del", "como", "mas", "más", "pero", "si", "ya", "muy", "este", "esta",
    "eso", "esto", "hay", "ser", "soy", "son", "tiene", "tengo", "todo",
    "bien", "hola", "gracias", "buenas", "buenos", "dias", "días",
})
# Defaults de fallback si el archivo no existe (vocabulario tech genérico).
_DEFAULT_THEMATIC_TOKENS = [
    "alexa", "echo", "windows", "win", "pc", "rutina", "rutinas", "dispositivo",
    "dispositivos", "luz", "luces", "bombilla", "enchufe", "actualizacion",
    "actualización", "driver", "drivers", "sistema", "ordenador", "movil",
    "móvil", "app", "aplicacion", "aplicación", "configurar", "instalar",
]
_EXCLUDED_TOKENS = _STOPWORDS_ES | {
    t.lower() for t in load_terms("classifier_excluded_tokens.txt", _DEFAULT_THEMATIC_TOKENS)
}


def _tokenize(text: str) -> list[str]:
    """Tokeniza texto en palabras (mín 2 chars), eliminando tokens neutros que
    no aportan señal al clasificador (stop-words + vocabulario temático)."""
    return [t for t in _WORD_RE.findall(text) if t.lower() not in _EXCLUDED_TOKENS]


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
    prior_ham = 1 - prior_spam
    log_p_spam = math.log(prior_spam)
    log_p_ham = math.log(prior_ham)

    vocab = set(spam_counts) | set(ham_counts)
    V = len(vocab)

    tokens = _tokenize(text)
    if not tokens:
        return None

    for tok in tokens:
        # Laplace smoothing
        p_t_given_spam = (spam_counts.get(tok, 0) + 1) / (total_spam + V)
        p_t_given_ham = (ham_counts.get(tok, 0) + 1) / (total_ham + V)
        log_p_spam += math.log(p_t_given_spam)
        log_p_ham += math.log(p_t_given_ham)

    # Softmax para normalizar
    max_log = max(log_p_spam, log_p_ham)
    e_spam = math.exp(log_p_spam - max_log)
    e_ham = math.exp(log_p_ham - max_log)
    return e_spam / (e_spam + e_ham)


# ----------------- Detector combinado -----------------


def check_against_samples(
    text: str | None,
    spam_samples: list[str],
    ham_samples: list[str],
) -> tuple[int, str | None]:
    """Combina Cosine similarity (caso por caso) + Naive Bayes (probabilidad global).

    Resultados:
      - Cosine high (>0.8) Y Bayes high (>0.8) → 100 (ban casi seguro)
      - Cosine high (>0.8)                     → 80
      - Bayes high (>0.85)                     → 60 (señal estadística)
      - Cosine medio (>0.6)                    → 60
      - Cosine ham high (>0.5) o Bayes ham (<0.2) → -30 (cancela score)

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
    if spam_sim > 0.6:
        return 60, spam_match
    if p_spam is not None and p_spam > 0.85:
        return 50, "bayes"
    # Señal HAM (cancela score si alguien comparte vocabulario con un sample previo legítimo)
    if ham_sim > 0.5:
        return -30, None
    if p_spam is not None and p_spam < 0.2:
        return -20, None
    return 0, None
