"""Sorteo cripto falso de un famoso, leído de una captura.

Caso real (3-oct-2026, Windows 10): «Joka» entró y a los 6 s mandó una captura de
un tuit falso de Elon Musk: «New $2500 crypto giveaway | Is now LIVE on
WexPred.com Use my promo code ElonX». El OCR lo leyó entero y los detectores de
contenido dieron **0**: lo cazaron por suerte las señales de forma (jfm_fast +
foto). Y el aviso «No he hecho nada» salió ANTES de esa decisión, de modo que el
admin leyó que no se había actuado sobre alguien ya baneado.

Medido antes de desplegar sobre 440 textos reales de la base: el ancla nueva no
salta en ninguno, y el detector sigue disparando solo en las dos estafas ya
conocidas.
"""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from src.detectors import investment_scam as inv
from src.i18n import set_lang

# Texto EXACTO que sacó el OCR, ruido incluido.
JOKA = ("Elon Musk Y x @elonmusk Terafab.AI Joined June 2009 h 1,415 Following "
        "241.7M Followers | Posts ~ Replies Reposts A | Elon Musk Y + @elonmusk - 1h "
        "ago ON fi) New $2500 crypto giveaway | Is now LIVE on WexPred.com Use my "
        "promo code ElonX | O 28k 17 4.1K O 29K ih) 2M y. 0000 ?")


def _msg(text: str):
    return NS(text=text, caption=None, entities=[], caption_entities=[])


@pytest.fixture(autouse=True)
def _es():
    set_lang("es")
    yield
    set_lang("es")


def test_el_caso_real_dispara_por_su_contenido():
    """80 = ancla + «use my promo code» + primer mensaje. Solo llega a expulsión
    (kick ≥70); con la foto en el primer mensaje (first_msg_media, 70) pasa de
    150, que es ban y reporte. Lo importante es que ya no depende de la prisa."""
    h = inv.check(_msg(JOKA), is_first_msg=True)
    assert h.rule == "investment_scam"
    assert h.score >= 70, h
    assert h.payload["crypto_giveaway"] is True


@pytest.mark.parametrize("texto", [
    "Bitcoin airdrop for everyone, enter the bonus code MUSK2026 on cryptodrop.io",
    "Sorteo de bitcoin ya activo en ganacripto.com, usa mi código promocional ELON",
    "Gran regalo de USDT, introduce el código de regalo X50 y recíbelo al instante",
])
def test_variantes_del_mismo_timo(texto):
    assert inv.check(_msg(texto), is_first_msg=True)


@pytest.mark.parametrize("texto", [
    # Hablar de la estafa para avisar: no hay mecanismo de canje.
    "Cuidado con los crypto giveaway de Elon Musk que salen en YouTube, son estafa",
    "Beware of fake crypto giveaways, nobody will double your bitcoin",
    # Códigos promocionales normales en un grupo de informática.
    "Usa el código promocional de Amazon para el SSD, sale a 40 euros",
    "Use the promo code at checkout and the Windows key is cheaper",
    "Sorteo de una licencia de Windows 11 entre los miembros del grupo, ya activo",
    # Un sorteo de verdad, sin cripto.
    "Giveaway of a Raspberry Pi 5 is now live on the forum, use my referral code if you want",
])
def test_lo_que_no_es_el_timo_no_dispara(texto):
    assert not inv.check(_msg(texto), is_first_msg=True), texto


def test_el_ancla_sola_no_decide():
    """Guarda de dos señales: el ancla sin nada más no llega."""
    h = inv.check(_msg("crypto giveaway is now live on example.com for real"),
                  is_first_msg=False)
    assert not h


def test_el_ancla_no_se_externaliza():
    """Es estructural, como las otras dos: no vive en config/."""
    for f in Path("config/blacklist").rglob("*.txt"):
        assert "_GIVEAWAY" not in f.read_text()
    assert "_GIVEAWAY_RE" in Path("src/detectors/investment_scam.py").read_text()


# ------------------------------------------- el aviso no puede contradecir al ban

def _on_message():
    arbol = ast.parse(Path("src/handlers.py").read_text())
    return next(n for n in ast.walk(arbol)
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_message")


def test_on_message_difiere_el_aviso_de_imagen():
    llamadas = [n for n in ast.walk(_on_message()) if isinstance(n, ast.Call)
                and getattr(n.func, "id", None) == "_hits_de_la_imagen"]
    assert llamadas, "on_message debe leer la imagen"
    for c in llamadas:
        assert any(k.arg == "diferido" for k in c.keywords), \
            "sin diferir, el aviso sale antes de saber si se banea"


def test_el_aviso_solo_se_suelta_sin_accion():
    """Se suelta en los returns sin hits y tras decidir noop, nunca tras un ban."""
    fuente = ast.get_source_segment(Path("src/handlers.py").read_text(), _on_message())
    i = fuente.index("decision = decide(")
    tras = fuente[i:fuente.index("_soltar_aviso_imagen", i)]
    assert 'decision.action == "noop"' in tras
    assert fuente.count("_soltar_aviso_imagen(") == 3


@pytest.mark.asyncio
async def test_diferido_no_manda_y_soltar_si(monkeypatch):
    from src import handlers

    enviados = []

    async def _avisar(*a, **k):
        enviados.append(a)

    monkeypatch.setattr(handlers, "_avisar_imagen_dudosa", _avisar)
    pendiente = [("texto", 0, "motivo")]
    await handlers._soltar_aviso_imagen(None, None, None, None, None, pendiente)
    assert len(enviados) == 1 and not pendiente
    await handlers._soltar_aviso_imagen(None, None, None, None, None, pendiente)
    assert len(enviados) == 1, "no se manda dos veces"
