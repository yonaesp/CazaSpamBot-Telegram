"""Tests del detector investment_scam (testimonio de estafa de inversión).

Foco anti-falso-positivo: el relato "di dinero y me devolvieron más" es la firma,
pero frases legítimas con verbos parecidos (devolver el cambio, invertir tiempo,
prestar dinero) NO deben disparar.
"""
from __future__ import annotations

import unicodedata
from types import SimpleNamespace

from src.detectors import investment_scam as det


def _msg(text):
    return SimpleNamespace(text=text, caption=None)


# ------------------------------- POSITIVOS -------------------------------

# El caso real que motivó el detector (grupo en inglés, primer mensaje).
REAL_SPAM = (
    "Mrs RafaelMarrero7 has been so good to me. I gave her 25,000 Rs, and after "
    "12 hours, she gave me 318,000Rs. 👇 @RafaelMarrero7"
)


def test_caso_real_con_mencion_dispara():
    hit = det.check(_msg(REAL_SPAM), is_first_msg=True)
    assert hit is not None and hit.rule == "investment_scam"
    assert hit.score >= 100  # nivel ban holgado
    assert hit.payload["profit"] is True


def test_caso_real_sin_mencion_sigue_disparando():
    """El objetivo del user: cazarlo aunque NO mencione a nadie."""
    sin_mencion = REAL_SPAM.rsplit("👇", 1)[0].strip()
    assert "@" not in sin_mencion
    hit = det.check(_msg(sin_mencion), is_first_msg=True)
    assert hit is not None and hit.rule == "investment_scam"
    assert hit.score >= 100  # sigue en nivel ban sin la mención
    assert hit.payload["profit"] is True


SPANISH_SPAM = (
    "La Sra. Ana me cambió la vida. Le entregué 500€ y en 24 horas me devolvió "
    "6.000€. Escríbele por privado, es de confianza."
)


def test_variante_espanola_dispara():
    hit = det.check(_msg(SPANISH_SPAM), is_first_msg=True)
    assert hit is not None and hit.rule == "investment_scam"
    assert hit.score >= 100
    assert hit.payload["profit"] and hit.payload["has_praise"]


def test_variante_espanola_nfd_sigue_disparando():
    """Mismo mensaje con acentos en forma NFD (combining) sigue cazándose."""
    nfd = unicodedata.normalize("NFD", SPANISH_SPAM)
    hit = det.check(_msg(nfd), is_first_msg=True)
    assert hit is not None and hit.score >= 100


FOREX_SPAM = (
    "I invested $500 with an expert forex trader and withdrew $6000 after 3 days. "
    "Thanks to her, God bless her!"
)


def test_variante_forex_ingles_dispara():
    hit = det.check(_msg(FOREX_SPAM), is_first_msg=True)
    assert hit is not None and hit.rule == "investment_scam"
    assert hit.score >= 100
    assert hit.payload["profit"] and hit.payload["has_time_window"]


def test_dispara_tambien_sin_ser_primer_mensaje():
    """La ganancia direccional es señal fuerte; el trust protege a veteranos aparte."""
    hit = det.check(_msg(SPANISH_SPAM), is_first_msg=False)
    assert hit is not None and hit.score >= 70


# ------------------------------- ANTI-FP -------------------------------

def test_cambio_del_camarero_no_dispara():
    """Relato de dar/recibir pero lo devuelto es MENOR (cambio): sin ganancia."""
    hit = det.check(
        _msg("I gave the waiter 50 dollars and he gave me 5 dollars back, nice guy"),
        is_first_msg=True,
    )
    assert hit is None or hit.score < 70


def test_invertir_tiempo_sin_cifras_no_dispara():
    hit = det.check(
        _msg("I invested a lot of time in my studies and finally earned my degree, so happy today"),
        is_first_msg=True,
    )
    assert hit is None or hit.score < 70


def test_prestamo_sin_verbo_de_retorno_no_dispara():
    """Sin la mitad de 'retorno' del relato, la puerta ni se abre."""
    hit = det.check(
        _msg("I sent you 20€ for the tickets, you can pay me back whenever you want"),
        is_first_msg=True,
    )
    assert hit is None or hit.score == 0


def test_solo_recibir_dinero_no_dispara():
    """Un único 'me dio X' (sin entrega previa con ganancia) no basta."""
    hit = det.check(
        _msg("Thank you, she gave me 5000€ that she owed me from last month, all good now"),
        is_first_msg=False,
    )
    assert hit is None or hit.score < 70


def test_mensaje_corto_no_se_evalua():
    hit = det.check(_msg("invested and earned"), is_first_msg=True)
    assert hit is None or hit.score == 0


def test_charla_normal_de_dinero_no_dispara():
    """Comentario cotidiano sobre precios, sin relato de retorno con ganancia."""
    hit = det.check(
        _msg("Me compré un móvil nuevo por 300€, el viejo lo vendí por 100€ en Wallapop"),
        is_first_msg=True,
    )
    assert hit is None or hit.score < 70
