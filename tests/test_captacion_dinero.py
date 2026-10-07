"""El guion del «dinero extra» que se cierra por privado.

Caso real (8-oct-2026, Windows 10): «Natalia» escribió a las 46 h de entrar un
mensaje de captación sin cifras ni enlace. `commercial_ad` sumaba 50 («ganar
dinero» + «envíame un mensaje» + primer mensaje), por debajo de 60, y solo lo paró
el clasificador aprendido con un mute. El admin pidió ban y reporte directos.

Medido antes de desplegar sobre 524 textos reales de la base: cambia de
puntuación solo este mensaje (0 → 155).
"""
from types import SimpleNamespace as NS

import pytest

from src import handlers
from src.detectors import commercial_ad as comad
from src.i18n import set_lang
from src.scoring import Decision

NATALIA = (
    "Si alguna vez has querido ganar dinero extra pero no sabes por dónde empezar, "
    "puedo compartir contigo algo que estoy haciendo.\nEs fácil de seguir y estoy "
    "obteniendo buenos resultados. También puedo explicárselo a cualquiera que "
    "quiera saber más; solo envíame un mensaje."
)
EN = (
    "If you've ever wanted to earn extra money but don't know where to start, I can "
    "share with you something I'm doing. It's easy to follow and I'm getting great "
    "results. I can explain it to anyone who wants to know more, just send me a message."
)


@pytest.fixture(autouse=True)
def _es():
    set_lang("es")
    yield
    set_lang("es")


def _m(text):
    return NS(text=text, caption=None)


@pytest.mark.parametrize("texto", [NATALIA, EN])
def test_el_guion_llega_a_ban_y_reporte(texto):
    h = comad.check(_m(texto), is_first_msg=True)
    assert h.rule == "commercial_ad"
    assert h.score >= 150, h
    assert h.payload["has_money_dm"] and h.payload["teasers"] >= 2
    dec = Decision(action="ban", score=h.score, rule=h.rule, reason=h.reason, payload={})
    assert handlers._is_reportable(dec), "commercial_ad ≥150 debe reportarse"


def test_sin_ser_primer_mensaje_sigue_siendo_ban():
    assert comad.check(_m(NATALIA), is_first_msg=False).score >= 100


@pytest.mark.parametrize("texto", [
    # Ayuda corriente: ganchos y privado, pero sin oferta de dinero.
    "Si no sabes por dónde empezar, escríbeme por privado y te paso la guía para instalar Windows 11",
    "Puedo compartir contigo el driver que estoy usando, es fácil de seguir el tutorial, escríbeme",
    "Con este ajuste del BIOS estoy obteniendo buenos resultados, a quien quiera saber más que me escriba",
    "If you don't know where to start, DM me and I can share with you the install guide",
    # Hablar de dinero sin guion ni privado.
    "¿Alguien sabe si se puede ganar dinero con un blog de Windows? Lo pregunto por curiosidad",
    "Busco ganar dinero extra arreglando ordenadores, ¿qué opináis del precio por hora?",
])
def test_lo_que_no_es_el_guion_no_actua(texto):
    h = comad.check(_m(texto), is_first_msg=True)
    assert h.score < 70, (h.score, texto)


def test_los_ganchos_no_cuentan_sin_oferta_de_dinero():
    txt = ("Si alguna vez has querido aprender PowerShell pero no sabes por dónde empezar, "
           "puedo compartir contigo algo que estoy haciendo, es fácil de seguir")
    h = comad.check(_m(txt), is_first_msg=True)
    assert not h or h.payload["teasers"] == 0


def test_un_solo_gancho_no_completa_el_guion():
    txt = "Gana dinero desde casa, puedo compartir contigo el método, escríbeme por privado"
    h = comad.check(_m(txt), is_first_msg=True)
    assert h.payload["teasers"] == 1
    assert h.score < 150
