"""Catálogo de reventa de licencias en inglés (caso real 30-sep-2026, Windows 10).

Cuenta «Adobe» (@Adobe_Global): «ADOBE REDEEM CODE ( 1month - 12months ) —>
( Warranty full )», Creative Cloud, CapCut Pro, Office Pro Plus, ChatGPT Pro…
Puntuaba 45 (solo las líneas con emoji) y lo tuvo que banear el admin a mano.
Medido tras el cambio sobre 503 mensajes reales: solo cambia este.
"""
from __future__ import annotations

from types import SimpleNamespace

from src.detectors import commercial_ad as ca

ADOBE = """✈️✈️✈️✈️✈️✈️✈️✈️✈️✈️

📙 ADOBE REDEEM CODE
|
|___ ( 1month - 12months )
—> ( Warranty full )
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
📒 ADOBE CREATIVE CLOUD PRO PLUS
I __ ( 25user - 5.000user )
—> ( Warranty full )
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
📘 CAPCUP PRO
I __ ( 1months - 12months )
📖 OFFICE PRO PLUS
📔 CHAT GPT PRO

💸 Price: …"""


def _score(txt, primero=True):
    h = ca.check(SimpleNamespace(text=txt, caption=None), is_first_msg=primero)
    return h.score if h else 0


def test_el_caso_real_se_banea():
    assert _score(ADOBE) >= 100


def test_una_conversacion_con_varias_marcas_no_cae():
    """Un grupo de Windows nombra estas marcas a diario."""
    for txt in (
        "Yo uso Office, Photoshop y ChatGPT en Windows 11 y va todo fluido, ¿a vosotros?",
        "Tengo Adobe, Office, CapCut y Canva instalados y el portátil va lento, ¿qué desinstalo?",
        "How do I redeem code from the Microsoft Store? It says invalid",
        "The laptop came with full warranty and Office preinstalled",
        "Contraté 1 month - 12 months de Spotify y no me deja cancelar",
    ):
        assert _score(txt) < 60, txt


def test_el_catalogo_solo_no_decide():
    """Cinco marcas sin nada más: 40 + primer mensaje 15 = 55, por debajo de 60."""
    assert _score("Comparativa: Adobe, Office, CapCut, Canva y ChatGPT, ¿cuál merece la pena pagar?") < 60


def test_marcas_distintas_no_cuenta_repeticiones():
    assert ca._marcas_distintas("adobe ADOBE Adobe office Office") == 2
    assert ca._marcas_distintas("CAPCUP PRO y CapCut") == 1
