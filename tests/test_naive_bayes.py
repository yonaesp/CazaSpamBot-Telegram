"""Tests para naive_bayes_spam_prob + check_against_samples combinado."""
from __future__ import annotations

import pytest

from src import learning


SPAM_SAMPLES = [
    "compra criptomonedas gana dinero",
    "trabajo desde casa 5000 euros",
    "haz click aquí y multiplica",
    "inversión segura 200% rentabilidad",
    "join my channel for crypto signals",
    "earn money easy daily payout",
    "click bit ly trabajo online",
    "envío fotos privadas premium",
    "casino bonus gratis hoy",
    "préstamo rápido sin avales",
    "venta de likes y seguidores",
    "compra seguidores instagram garantizado",
]

HAM_SAMPLES = [
    "alguien sabe cómo configurar la rutina de Alexa",
    "no me funciona el HDMI con Windows 11",
    "buenas, ¿cómo va el grupo?",
    "tengo problema con Windows update",
    "compré una luz Yeelight y va genial",
    "Alexa no entiende cuando le hablo en gallego",
    "actualicé a Win11 y va más lento",
    "alguien tiene un router compatible con Home Assistant",
    "compré una bombilla Tapo y muy bien",
    "se puede hacer rutina con el Echo Dot",
    "windows me da pantallazo azul al cargar",
    "instalé linux dual boot y funciona",
]


def test_below_min_samples_returns_none():
    """Sin samples suficientes, Bayes no actúa."""
    out = learning.naive_bayes_spam_prob("trabajo crypto", ["a"], ["b"])
    assert out is None


def test_clear_spam_text():
    """Texto típicamente spam → probabilidad alta."""
    p = learning.naive_bayes_spam_prob(
        "gana dinero compra criptomonedas premium",
        SPAM_SAMPLES, HAM_SAMPLES,
    )
    assert p is not None
    assert p > 0.7, f"esperaba >0.7, got {p}"


def test_clear_ham_text():
    """Texto típicamente legítimo → probabilidad baja."""
    p = learning.naive_bayes_spam_prob(
        "alguien tiene problema con Alexa y rutina",
        SPAM_SAMPLES, HAM_SAMPLES,
    )
    assert p is not None
    assert p < 0.3, f"esperaba <0.3, got {p}"


def test_check_against_samples_combines():
    """check_against_samples integra Bayes + Cosine."""
    score, match = learning.check_against_samples(
        "alguien sabe cómo configurar Alexa rutina",
        SPAM_SAMPLES, HAM_SAMPLES,
    )
    # debería ser negativo (penalización) por Bayes ham low o cosine ham match
    assert score <= 0


def test_check_against_samples_spam_clear():
    score, match = learning.check_against_samples(
        "gana dinero trabajo crypto desde casa fácil",
        SPAM_SAMPLES, HAM_SAMPLES,
    )
    assert score >= 50  # Bayes >0.85 o cosine alto


def test_check_against_samples_no_samples():
    """Sin samples, no actúa."""
    score, match = learning.check_against_samples("texto random", [], [])
    assert score == 0
    assert match is None


def test_tokenize_unicode():
    """Tokenizer maneja español + chars unicode, excluyendo stop-words."""
    tokens = learning._tokenize("comprar criptomonedas baratas ahora")
    # palabras con señal se mantienen
    assert "comprar" in tokens
    assert "criptomonedas" in tokens
    assert "baratas" in tokens


def test_tokenize_excluye_stopwords_y_tematicas():
    """Stop-words y vocabulario temático (alexa/windows) se eliminan."""
    tokens = learning._tokenize("hola que tal con alexa y windows")
    assert "hola" not in tokens   # stop-word
    assert "alexa" not in tokens  # temático
    assert "windows" not in tokens


def test_bayes_with_very_short_text():
    """Texto sin tokens → None."""
    p = learning.naive_bayes_spam_prob("a", SPAM_SAMPLES, HAM_SAMPLES)
    assert p is None  # menos de min token len
