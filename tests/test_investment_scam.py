"""Detector de testimonio de estafa de multiplicación de dinero.

Caso real que lo originó (grupo de domótica): «Mrs RafaelMarrero7 has been so
good to me. I gave her 25,000 Rs, and after 12 hours, she gave me 318,000 Rs. 👇
@RafaelMarrero7». Antes solo lo cazaba external_mention por el @usuario final;
sin esa mención puntuaba 0 y se colaba. Estos tests fijan que se cace por el
testimonio en sí, y sobre todo que NO castigue conversación normal sobre dinero.
"""
from types import SimpleNamespace as NS

import pytest

from src.detectors import investment_scam as inv
from src.i18n import set_lang


def _msg(text: str):
    return NS(text=text, caption=None, entities=[], caption_entities=[])


@pytest.fixture(autouse=True)
def _es():
    set_lang("es")
    yield
    set_lang("es")


# El caso real, con y SIN la mención final (que era lo único que lo cazaba antes).
@pytest.mark.parametrize("texto", [
    "Mrs RafaelMarrero7 has been so good to me. I gave her 25,000 Rs, and after 12 hours, "
    "she gave me 318,000Rs. 👇 @RafaelMarrero7",
    "Mrs RafaelMarrero7 has been so good to me. I gave her 25,000 Rs, and after 12 hours, "
    "she gave me 318,000Rs.",
])
def test_caso_real_con_y_sin_mencion(texto):
    assert inv.check(_msg(texto), is_first_msg=True).score >= 60


@pytest.mark.parametrize("texto", [
    "Thanks to Mr James, I invested $500 and withdrew $6000 after 24 hours. He is so legit, DM him now!",
    "Gracias a la señora Sofía, le di 20000 pesos y me devolvió 250000 en 12 horas. Es de confianza, contáctala 👇",
    "I recommend her, she changed my life. Sent 10,000 and got 120,000 back. Message her now",
    "Mr Wong has been so good to me, invested 5000 USDT and got 45000 USDT in 48 hours, trust him",
])
def test_variantes_de_la_estafa(texto):
    assert inv.check(_msg(texto), is_first_msg=True).score >= 60, f"no cae: {texto!r}"


@pytest.mark.parametrize("texto", [
    # Hablar de dinero con toda normalidad no es spam. Ninguna debe disparar.
    "I paid $500 for my GPU last year and it was worth every cent honestly",
    "My salary is about 2000 euros a month, is that normal for a junior role?",
    "Thanks John, you helped me fix my Windows install, you're the best",
    # Trampa 1: inversion legitima. «worth» NO es verbo de retorno, no hay ancla.
    "I invested 1000 in an index fund and now it's worth 1500, slow but steady",
    "I lost 500 in the market last year, painful lesson about leverage",
    # Trampa 2: ancla presente pero sin ninguna senial de estafa (solo 1 senial).
    "I gave my brother 50 bucks and he paid me back 100 for covering his ticket",
    # Trampa 3: elogio a una persona pero sin ancla ni CTA (solo 1 senial).
    "Mrs Smith is my math teacher, she has been so good to me this semester",
    "Bitcoin went from 20k to 60k this year, wild ride for holders",
    "Alguien sabe si Windows Update rompe el arranque tras actualizar?",
    "Contáctame si quieres el driver de la placa, lo tengo por aquí guardado",
    # Un simple "DM me" no es estafa.
    "DM me if you need the config file, happy to share it with anyone",
])
def test_conversacion_normal_no_dispara(texto):
    for first in (True, False):
        assert inv.check(_msg(texto), is_first_msg=first).score == 0, f"falso positivo: {texto!r}"


def test_ancla_sola_no_basta():
    """El ancla numerica sin senial de estafa no llega al umbral: alguien puede
    contar que dio X y recibio mas sin ser un timo (una apuesta, un favor)."""
    solo_ancla = "I gave 100 and received 500 back that day, lucky me at the casino"
    assert inv.check(_msg(solo_ancla), is_first_msg=True).score == 0


def test_multiplicador_debe_ser_mayor():
    """«di X y me devolvieron menos» no es el patron del timo."""
    menor = "Mrs X has been so good to me, I gave her 500 and she gave me back 200"
    # aunque haya elogio, sin ancla (retorno menor) queda en 1 senial
    assert inv.check(_msg(menor), is_first_msg=True).score == 0


def test_rupias_y_monedas_exoticas_se_reconocen():
    """El importe en Rs/₦/USDT debe contar dentro del ancla."""
    txt = "She has been so good to me. I sent 15,000 Rs and received 200,000 Rs after 10 hours, DM her"
    assert inv.check(_msg(txt), is_first_msg=True).score >= 60


def test_texto_corto_no_dispara():
    assert inv.check(_msg("gané 500"), is_first_msg=True).score == 0


def test_reason_traducido_en_ambos_idiomas():
    txt = ("Mrs RafaelMarrero7 has been so good to me. I gave her 25,000 Rs, and after 12 hours, "
           "she gave me 318,000Rs.")
    for lang in ("es", "en"):
        set_lang(lang)
        h = inv.check(_msg(txt), is_first_msg=True)
        assert h.reason and "reason." not in h.reason, f"reason sin traducir en {lang}: {h.reason}"
