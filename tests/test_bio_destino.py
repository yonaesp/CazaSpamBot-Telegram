"""La bio con un enlace privado que no llega a `bio_spam` (L58, caso Rosario, 8-nov-2026).

Entró en Alexa con solo `t.me/+…` en la bio (40 puntos; el ban empieza en 60), pasó el
botón en 47 s y once días después publicó un testimonio de inversión con un enlace a
«Trade Republic investment Fx📊» («90% de precisión · 100% de rentabilidad»), que el
juez de destinos dio por limpio.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from src import handlers, link_reader, recien_llegados
from src.db import DB
from src.detectors import link_target
from src.detectors.link_target import promesa_de_rentabilidad

CHAT = -1001156069668
DESCRIPCION_REAL = (
    "La mejor compañía de inversión 📊 ayuda a más de 2 millones de clientes a alcanzar sus "
    "objetivos financieros mediante operaciones e inversiones sencillas.\n\n📈📉📈💷📊\n\n"
    "90% de precisión\n📶 100% de rentabilidad\n📶 Selección instantánea ✅\n@Trader_Alice00"
)


def _destino(titulo="Trade Republic investment Fx📊️️", descripcion=DESCRIPCION_REAL, chat_id=-100555):
    return link_reader.Destino(titulo=titulo, descripcion=descripcion, url="https://t.me/+X", chat_id=chat_id)


# ------------------------------------------------------- el juez de destinos

def test_el_destino_real_ya_no_sale_limpio():
    hit = link_target.check(_destino())
    assert hit and hit.rule == "link_target_spam"


@pytest.mark.parametrize("texto", [
    "Forex signals · 95% accuracy · join now",
    "Guaranteed profits every day",
    "Ganancias garantizadas desde el primer día",
    "Trading de cripto: 85% de aciertos",
])
def test_promesas_de_rentabilidad(texto):
    assert promesa_de_rentabilidad(texto)


@pytest.mark.parametrize("texto", [
    "OCR con 99% de precisión para tus PDF",
    "Broker MQTT con 99,9% de efectividad",
    "Grupo de investigación: modelo con 95% de precisión",
    "Medidor de señales wifi con 95% de precisión",
    "Criptografía para todos: 99% de efectividad",
    "Inversión a largo plazo: indexados y ETF, sin prisas",
    "Rentabilidad pasada no garantiza rentabilidades futuras. Inversión responsable.",
    "Aquí avisamos: no existe la rentabilidad garantizada. Cuidado con el trading.",
    "Ofertas de Amazon con 70% de descuento",
])
def test_lo_que_no_es_una_promesa(texto):
    assert not promesa_de_rentabilidad(texto)
    assert not link_target.check(_destino(titulo="Canal", descripcion=texto))


@pytest.mark.parametrize("titulo", ["Baby blog España 💦 🍑", "Chicas 🥵👅 solo hoy"])
def test_dos_emojis_sexuales_distintos_confiesan(titulo):
    """Destinos reales de las bios baneadas: el reclamo va en emojis, no en palabras."""
    assert link_target.check(_destino(titulo=titulo, descripcion=""))


@pytest.mark.parametrize("titulo", [
    "Private 💋.",                 # uno solo: a revisión, no a ban
    "Ofertas 🔥🔥😈 Amazon",        # 🔥 y 😈 no cuentan
    "Frutería 🍑🍑",                # el mismo dos veces no son dos
    "Cursway ✈️ AI travel planner",
])
def test_lo_que_no_confiesa_por_emojis(titulo):
    assert not link_target.check(_destino(titulo=titulo, descripcion=""))


# ------------------------------------------------- leer el destino de la bio

@pytest.fixture
def entorno(tmp_path, monkeypatch):
    db = DB(str(tmp_path / "t.db"))
    cfg = NS(mode="active", shadow=False)
    aplicar, revisar = AsyncMock(), AsyncMock()
    monkeypatch.setattr(handlers, "_apply_action", aplicar)
    monkeypatch.setattr(handlers, "_revision_humana", revisar)
    monkeypatch.setattr(handlers, "_se_modera", lambda db, cfg, cid: cid == CHAT)
    leido = {}

    def poner_destino(destino):
        async def leer(context, urls, **kw):
            leido["urls"] = urls
            return destino
        monkeypatch.setattr(link_reader, "leer", leer)
    return NS(db=db, cfg=cfg, aplicar=aplicar, revisar=revisar, poner=poner_destino, leido=leido)


USER = NS(id=8528059069, username=None, first_name="Rosario")
BIO = "https://t.me/+WcrsCd2W0ZZkYjM0"


async def _revisar(e, bio=BIO):
    return await recien_llegados.revisar_destino_bio(NS(bot_data={}), e.db, e.cfg, CHAT, "Alexa", USER, bio, "join")


@pytest.mark.asyncio
async def test_destino_que_se_confiesa_spam_es_ban(entorno):
    entorno.poner(_destino())
    assert await _revisar(entorno) is True
    kw = entorno.aplicar.await_args.kwargs
    assert kw["decision"].action == "ban" and kw["decision"].rule == "bio_spam"
    # La bio va en el payload: así se ficha el enlace (`destinos.aprender_de_ban`).
    assert kw["decision"].payload["bio_preview"] == BIO
    assert entorno.leido["urls"] == ["https://t.me/+WcrsCd2W0ZZkYjM0"]
    entorno.revisar.assert_not_awaited()


@pytest.mark.asyncio
async def test_destino_limpio_va_a_revision_una_sola_vez(entorno):
    entorno.poner(_destino(titulo="Familia García", descripcion="Fotos de la familia"))
    assert await _revisar(entorno) is False
    assert await _revisar(entorno) is False
    assert entorno.revisar.await_count == 1
    motivo, params = entorno.revisar.await_args.args[5][0]
    assert motivo == "bio_enlace_privado" and params["destino"] == "Familia García"
    assert entorno.db.tiene_accion(USER.id, recien_llegados.REGLA_REVISION_BIO)
    entorno.aplicar.assert_not_awaited()


@pytest.mark.asyncio
async def test_enlace_caducado_va_a_revision_sin_destino(entorno):
    entorno.poner(None)
    await _revisar(entorno)
    assert entorno.revisar.await_args.args[5][0][0] == "bio_enlace_privado_ilegible"


@pytest.mark.asyncio
async def test_enlace_a_un_grupo_propio_no_hace_nada(entorno):
    entorno.poner(_destino(titulo="Alexa", descripcion="", chat_id=CHAT))
    assert await _revisar(entorno) is False
    entorno.revisar.assert_not_awaited()
    entorno.aplicar.assert_not_awaited()


@pytest.mark.asyncio
async def test_bio_sin_enlace_privado_ni_se_lee(entorno):
    entorno.poner(_destino())
    assert await _revisar(entorno, bio="Mi canal: t.me/canalpublico") is False
    assert "urls" not in entorno.leido


# --------------------------------------------------- enganchado en los dos sitios

def _fn(path, nombre):
    return next(n for n in ast.walk(ast.parse(Path(path).read_text(encoding="utf-8")))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre)


def test_la_entrada_lo_lanza_aparte():
    """En el join, en una tarea: es una llamada por la cuenta secundaria."""
    fn = _fn("src/handlers.py", "on_chat_member")
    tareas = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
              and getattr(n.func, "attr", "") == "create_task"
              and "revisar_destino_bio_aparte" in ast.unparse(n)]
    assert tareas


def test_el_repaso_lo_mira_tras_bio_spam():
    src = ast.unparse(_fn("src/recien_llegados.py", "_revisar_perfil"))
    assert "await revisar_destino_bio(" in src
    assert src.index("bio_spam.check(") < src.index("await revisar_destino_bio(")
