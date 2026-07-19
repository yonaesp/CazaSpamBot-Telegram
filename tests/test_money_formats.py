"""El importe se escribe distinto en cada idioma: 500€ (es) y $500 (en).

Antes solo se reconocía la forma española, así que un «Earn $500/day» en un
grupo en inglés no sumaba señal de dinero y el anuncio se colaba entero.
"""
from types import SimpleNamespace as NS

import pytest

from src.detectors import commercial_ad as ca
from src.i18n import set_lang


def _msg(text: str):
    return NS(text=text, caption=None, entities=[], caption_entities=[])


@pytest.fixture(autouse=True)
def _es_al_salir():
    yield
    set_lang("es")


@pytest.mark.parametrize("texto", [
    "$500", "$2000", "$2,000", "$1.500", "€300", "£250", "$5k",
    "500€", "2.000 €", "300 EUR", "1500 USD",
])
def test_importes_reconocidos_en_ambos_formatos(texto):
    assert ca.money_re().search(texto), f"no reconoce el importe {texto!r}"


@pytest.mark.parametrize("texto", [
    "$500/day", "$500 per day", "$2000 per month", "$300 a week",
    "$100 daily", "500 USD weekly",
    "2.800 € al mes", "500€ semanales", "3000 dólares por mes",
])
def test_periodicidad_en_ambos_idiomas(texto):
    assert ca._periodic_money_re().search(texto), f"no reconoce la periodicidad en {texto!r}"


def test_spam_ingles_con_importe_se_detecta():
    set_lang("en")
    hit = ca.check(_msg(
        "🔥 NOW HIRING! Earn $500/day working from home. "
        "No experience needed. DM me for details"
    ))
    assert hit.score >= 60, f"spam evidente en inglés no detectado (score={hit.score})"


@pytest.mark.parametrize("texto", [
    # Gente hablando de dinero con toda normalidad. Ninguna debe disparar:
    # falsos positivos son peores que falsos negativos en este proyecto.
    "I paid $500 for this GPU last year and honestly it was worth every cent",
    "The subscription is $10 a month which is cheaper than the alternatives",
    "My salary is around $3000 per month, is that normal for a junior role?",
    "Me pagaron 2000€ el mes pasado en mi trabajo, no está mal para empezar",
    "La suscripción cuesta 10€ al mes, más barato que las alternativas",
])
def test_hablar_de_dinero_no_es_spam(texto):
    for lang in ("es", "en"):
        set_lang(lang)
        assert ca.check(_msg(texto)).score == 0, f"falso positivo en {lang}: {texto!r}"
