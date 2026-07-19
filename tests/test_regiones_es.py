"""Español de América: monedas locales y voseo rioplatense.

El bot nació en un grupo de España, así que el spam laboral latinoamericano
(«ganá X pesos por día, contactame») pasaba limpio: ni la moneda, ni la
periodicidad «por día», ni el imperativo voseante estaban contemplados.
Todo esto vive ahora en config/blacklist/, editable por cada admin.
"""
from types import SimpleNamespace as NS

import pytest

from src.detectors import commercial_ad as ca
from src.i18n import set_lang


def _msg(text: str):
    return NS(text=text, caption=None, entities=[], caption_entities=[])


@pytest.fixture(autouse=True)
def _es():
    set_lang("es")
    yield
    set_lang("es")


@pytest.mark.parametrize("texto", [
    "5000 pesos", "2000 ARS", "R$ 1.500", "S/ 300", "50000 COP",
    "$3000 MXN", "1500 CLP", "500€", "$500",
])
def test_monedas_de_varias_regiones(texto):
    assert ca.money_re().search(texto), f"no reconoce {texto!r}"


@pytest.mark.parametrize("texto", [
    "Trabajo desde casa, gana 5000 pesos por día. Escríbeme al privado para más info",
    "Ganá 3000 ARS al día trabajando desde tu celular. Contactame por privado",
])
def test_spam_laboral_latinoamericano(texto):
    assert ca.check(_msg(texto)).score >= 60, "spam evidente sin detectar"


@pytest.mark.parametrize("texto", [
    # Palabras de moneda usadas en su sentido corriente. Ninguna es spam.
    "El peso del paquete es de 3 kilos, no creo que salga caro el envío a casa",
    "Hoy hace un sol increíble, aprovecha para salir a andar un rato largo",
    "Necesito media libra de harina para la receta, ¿cuánto es eso en gramos?",
    "Me pusieron una corona en el dentista y dolió más la factura que la muela",
    "Esto es real, lo he probado yo mismo y funciona perfecto en mi equipo",
    # «al día» en su uso normal, que es constante en cualquier grupo.
    "Me tomo dos cafés al día y aun así llego tarde a todo, es desesperante",
    "Gasto como 10€ al día en comer fuera, debería cocinar más en casa",
    "Estoy al día con las actualizaciones y aun así me va lento el equipo",
    # Voseo en conversación normal: hablar así no es spam.
    "Che, escribime cuando puedas y lo vemos con calma, no hay apuro ninguno",
    "Si querés sumate al grupo de fotos que armamos, está bastante tranquilo",
    "Contactame si necesitás una mano con el tema del driver de la placa",
    "Estoy trabajando desde casa esta semana porque me arreglan la oficina",
])
def test_conversacion_normal_no_es_spam(texto):
    assert ca.check(_msg(texto)).score == 0, f"falso positivo: {texto!r}"
