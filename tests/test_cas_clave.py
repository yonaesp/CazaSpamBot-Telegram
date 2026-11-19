"""CAS pide clave: un rechazo no es «limpio», y el admin se entera (L65).

Caso real (19-nov-2026): la API de CAS empezó a contestar 401 «API key required» a
todo. El bot leía `ok: false`, guardaba 0 antecedentes en la caché y seguía: 60
personas apuntadas como limpias en tres días sin que CAS hubiera dicho nada de ellas,
y ni una línea en el log.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from src import cas_vigia
from src.detectors import cas

CLAVE = "clave-secreta-de-prueba"
TTL = 86400


class _Respuesta:
    def __init__(self, status=200, datos=None, error=None):
        self.status, self._datos, self._error = status, datos, error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self, content_type=None):
        return self._datos


class _Sesion:
    """Imita lo que usa el detector de `aiohttp.ClientSession` y apunta cada llamada."""

    def __init__(self, respuesta):
        self.respuesta, self.llamadas = respuesta, []

    def get(self, url, **kw):
        self.llamadas.append((url, kw))
        return self.respuesta


RECHAZO = _Respuesta(401, {"ok": False, "error_code": 401, "description": "API key required"})
NO_ESTA = _Respuesta(200, {"ok": False, "description": "Record not found."})
FICHADO = _Respuesta(200, {"ok": True, "result": {"offenses": 3, "messages": ["x"]}})


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    monkeypatch.delenv(cas.ENV_CLAVE, raising=False)
    cas._ultimo_log.clear()
    cas.estado.update(rechazos=0, motivo="")


@pytest.fixture
def con_clave(monkeypatch):
    monkeypatch.setenv(cas.ENV_CLAVE, CLAVE)


# ---------- el detector ----------

@pytest.mark.asyncio
async def test_la_clave_va_en_la_cabecera_y_nunca_en_la_url(tmp_db, con_clave):
    s = _Sesion(FICHADO)
    await cas.check(5, s, tmp_db, TTL)
    (url, kw), = s.llamadas
    assert kw["headers"] == {"Authorization": f"Bearer {CLAVE}"}
    assert CLAVE not in url and CLAVE not in str(kw["params"])


@pytest.mark.asyncio
async def test_fichado_banea_y_se_recuerda(tmp_db, con_clave):
    hit = await cas.check(5, _Sesion(FICHADO), tmp_db, TTL)
    assert hit and hit.rule == "cas_match" and hit.payload == {"offenses": 3, "cached": False}
    assert tmp_db.cas_lookup(5, TTL) == 3


@pytest.mark.asyncio
async def test_quien_no_esta_en_la_lista_queda_limpio(tmp_db, con_clave):
    assert not await cas.check(5, _Sesion(NO_ESTA), tmp_db, TTL)
    assert tmp_db.cas_lookup(5, TTL) == 0


@pytest.mark.asyncio
async def test_un_rechazo_de_la_clave_no_se_guarda_como_limpio(tmp_db, con_clave, caplog):
    with caplog.at_level(logging.WARNING):
        assert not await cas.check(5, _Sesion(RECHAZO), tmp_db, TTL)
    assert tmp_db.cas_lookup(5, TTL) is None, "se apuntó como limpio a quien CAS no miró"
    assert cas.estado == {"rechazos": 1, "motivo": "API key required"}
    assert "API key required" in caplog.text and CLAVE not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("respuesta", [
    _Respuesta(429, {"ok": False, "error_code": 429, "description": "Too Many Requests"}),
    _Respuesta(500, {"ok": False}),
    _Respuesta(200, ["no", "es", "un", "dict"]),
    _Respuesta(200, {"ok": True, "result": {"offenses": "muchas"}}),
    _Respuesta(error=TimeoutError("tarda")),
])
async def test_una_respuesta_que_no_se_entiende_tampoco(tmp_db, con_clave, respuesta):
    assert not await cas.check(5, _Sesion(respuesta), tmp_db, TTL)
    assert tmp_db.cas_lookup(5, TTL) is None


@pytest.mark.asyncio
async def test_con_403_tambien_es_cosa_de_la_clave(con_clave):
    r = _Respuesta(403, {"ok": False, "description": "Invalid API key"})
    assert await cas.consultar(5, _Sesion(r)) == (cas.RECHAZADA, 0, "Invalid API key")


@pytest.mark.asyncio
async def test_sin_clave_no_se_llama_a_cas_ni_se_apunta_nada(tmp_db):
    s = _Sesion(FICHADO)
    assert not await cas.check(5, s, tmp_db, TTL)
    assert s.llamadas == [] and tmp_db.cas_lookup(5, TTL) is None


@pytest.mark.asyncio
async def test_lo_que_ya_se_sabia_vale_aunque_falte_la_clave(tmp_db):
    tmp_db.cas_store(5, 2)
    hit = await cas.check(5, _Sesion(RECHAZO), tmp_db, TTL)
    assert hit and hit.payload == {"offenses": 2, "cached": True}


@pytest.mark.asyncio
async def test_el_log_no_se_llena_con_la_misma_linea(tmp_db, con_clave, caplog):
    with caplog.at_level(logging.WARNING):
        for uid in range(20):
            await cas.check(uid, _Sesion(RECHAZO), tmp_db, TTL)
    assert caplog.text.count("CAS rechaza") == 1
    assert cas.estado["rechazos"] == 20


@pytest.mark.asyncio
async def test_la_clave_no_sale_en_el_motivo_de_un_fallo_de_red(con_clave):
    r = _Respuesta(error=RuntimeError(f"no conecta con cabecera Bearer {CLAVE}"))
    estado, _, motivo = await cas.consultar(5, _Sesion(r))
    assert estado == cas.SIN_RESPUESTA and CLAVE not in motivo


# ---------- el vigía ----------

def _ctx(db, respuesta=None, cas_enabled=True):
    return NS(
        bot=NS(send_message=AsyncMock()),
        bot_data={"cfg": NS(cas_enabled=cas_enabled, admin_notify_chat_id=42),
                  "db": db, "http": _Sesion(respuesta) if respuesta else None},
    )


def _textos(ctx):
    return [c.kwargs["text"] for c in ctx.bot.send_message.await_args_list]


@pytest.mark.asyncio
async def test_sin_clave_avisa_una_sola_vez(tmp_db):
    ctx = _ctx(tmp_db)
    await cas_vigia.comprobar_job(ctx)
    await cas_vigia.comprobar_job(ctx)  # otro arranque, mismo motivo
    assert len(_textos(ctx)) == 1
    assert "CAS_API_KEY" in _textos(ctx)[0] and "combot.org" in _textos(ctx)[0]
    assert ctx.bot.send_message.await_args.kwargs["disable_notification"] is False  # suena


@pytest.mark.asyncio
async def test_con_cas_apagado_a_proposito_no_dice_nada(tmp_db):
    ctx = _ctx(tmp_db, cas_enabled=False)
    await cas_vigia.comprobar_job(ctx)
    assert _textos(ctx) == []


@pytest.mark.asyncio
async def test_clave_rechazada_avisa_con_el_motivo(tmp_db, con_clave):
    r = _Respuesta(401, {"ok": False, "error_code": 401, "description": "Invalid <key>"})
    ctx = _ctx(tmp_db, r)
    await cas_vigia.comprobar_job(ctx)
    await cas_vigia.comprobar_job(ctx)
    assert len(_textos(ctx)) == 1
    assert "Invalid &lt;key&gt;" in _textos(ctx)[0] and CLAVE not in _textos(ctx)[0]


@pytest.mark.asyncio
async def test_un_corte_de_red_ni_avisa_ni_da_por_bueno(tmp_db, con_clave):
    ctx = _ctx(tmp_db, _Respuesta(error=TimeoutError("tarda")))
    await cas_vigia.comprobar_job(ctx)
    assert _textos(ctx) == [] and tmp_db.get_text_pref(cas_vigia.PREF_AVISADO) is None


@pytest.mark.asyncio
async def test_funcionando_de_siempre_no_dice_nada(tmp_db, con_clave):
    ctx = _ctx(tmp_db, NO_ESTA)
    await cas_vigia.comprobar_job(ctx)
    assert _textos(ctx) == [] and tmp_db.get_text_pref(cas_vigia.PREF_AVISADO) == cas_vigia.BIEN


@pytest.mark.asyncio
async def test_al_poner_la_clave_dice_que_vuelve(tmp_db, monkeypatch):
    ctx = _ctx(tmp_db, NO_ESTA)
    await cas_vigia.comprobar_job(ctx)            # sin clave: avisa
    monkeypatch.setenv(cas.ENV_CLAVE, CLAVE)
    await cas_vigia.comprobar_job(ctx)            # ya contesta: lo dice, callado
    await cas_vigia.comprobar_job(ctx)
    assert len(_textos(ctx)) == 2
    assert ctx.bot.send_message.await_args.kwargs["disable_notification"] is True


@pytest.mark.asyncio
async def test_si_el_aviso_no_sale_se_reintenta_al_dia_siguiente(tmp_db):
    from telegram.error import TelegramError
    ctx = _ctx(tmp_db)
    ctx.bot.send_message.side_effect = TelegramError("bloqueado")
    await cas_vigia.comprobar_job(ctx)
    ctx.bot.send_message.side_effect = None
    await cas_vigia.comprobar_job(ctx)
    assert ctx.bot.send_message.await_count == 2
    assert tmp_db.get_text_pref(cas_vigia.PREF_AVISADO) == cas_vigia.SIN_CLAVE


def test_el_vigia_esta_programado():
    from pathlib import Path
    fuente = (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")
    assert "run_repeating(cas_vigia.comprobar_job" in fuente
