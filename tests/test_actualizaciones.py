"""Aviso de versión nueva y parte de cómo fue la actualización (L51)."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import aiohttp
import pytest

from src import actualizaciones as act


@pytest.mark.parametrize("texto,esperado", [
    ("v1.2.3", (1, 2, 3)), ("1.10.0", (1, 10, 0)), (" v2.0.0 ", (2, 0, 0)),
    ("v1.2", None), ("v1.2.3-rc1", None), ("latest", None), (None, None), ("", None),
])
def test_version_tupla(texto, esperado):
    assert act.version_tupla(texto) == esperado


@pytest.mark.parametrize("url,repo", [
    ("https://github.com/yonaesp/CazaSpamBot-Telegram", "yonaesp/CazaSpamBot-Telegram"),
    ("https://github.com/alguien/mi-copia.git", "alguien/mi-copia"),
    ("https://github.com/alguien/mi-copia/", "alguien/mi-copia"),
    # Sin enlace o fuera de GitHub, las versiones del original.
    ("", "yonaesp/CazaSpamBot-Telegram"),
    ("https://gitlab.com/x/y", "yonaesp/CazaSpamBot-Telegram"),
])
def test_api_ultima_sigue_el_repo_de_repo_url(url, repo):
    assert act.api_ultima(url) == f"https://api.github.com/repos/{repo}/releases/latest"


@pytest.mark.parametrize("valor,activo", [(None, True), ("true", True), ("false", False),
                                          ("0", False), ("OFF", False), ("no", False)])
def test_update_check_viene_encendido(monkeypatch, valor, activo):
    if valor is None:
        monkeypatch.delenv("UPDATE_CHECK", raising=False)
    else:
        monkeypatch.setenv("UPDATE_CHECK", valor)
    assert act.activado() is activo


class _Respuesta:
    def __init__(self, status, datos=None, error=None):
        self.status, self._datos, self._error = status, datos, error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._datos


class _Sesion:
    def __init__(self, respuesta):
        self.respuesta, self.cabeceras = respuesta, None

    def get(self, url, headers=None, timeout=None):
        self.cabeceras = headers
        return self.respuesta


@pytest.mark.asyncio
@pytest.mark.parametrize("respuesta,esperado", [
    (_Respuesta(200, {"tag_name": "v1.1.0", "html_url": "https://x/r"}),
     {"tag": "v1.1.0", "url": "https://x/r"}),
    (_Respuesta(404), None),                                   # aún no hay ninguna publicada
    (_Respuesta(403, {"message": "rate limit"}), None),
    (_Respuesta(200, {"tag_name": "v1.1.0", "prerelease": True}), None),
    (_Respuesta(200, {"tag_name": "nightly"}), None),
    (_Respuesta(200, ["no", "es", "un", "dict"]), None),
    (_Respuesta(0, error=aiohttp.ClientConnectionError("sin red")), None),
    (_Respuesta(0, error=TimeoutError()), None),
])
async def test_ultima_version(respuesta, esperado):
    sesion = _Sesion(respuesta)
    assert await act.ultima_version(sesion, "u") == esperado
    assert sesion.cabeceras["User-Agent"].startswith("CazaSpamBot/")


def _ctx(tmp_db, admin=42):
    bot = NS(send_message=AsyncMock())
    return NS(bot=bot, bot_data={"cfg": NS(admin_notify_chat_id=admin), "db": tmp_db,
                                 "http": object()})


@pytest.mark.asyncio
async def test_avisa_una_sola_vez_por_version(tmp_db, monkeypatch):
    monkeypatch.delenv("UPDATE_CHECK", raising=False)
    monkeypatch.setattr(act, "__version__", "1.0.0")
    ultima = {"tag": "v1.1.0", "url": "https://github.com/x/y/releases/tag/v1.1.0"}
    monkeypatch.setattr(act, "ultima_version", AsyncMock(return_value=ultima))
    ctx = _ctx(tmp_db)
    await act.comprobar_job(ctx)
    await act.comprobar_job(ctx)
    ctx.bot.send_message.assert_awaited_once()
    kw = ctx.bot.send_message.await_args.kwargs
    assert kw["chat_id"] == 42 and "v1.1.0" in kw["text"] and "v1.0.0" in kw["text"]
    assert "./update.sh" in kw["text"] and ultima["url"] in kw["text"]
    assert kw["disable_notification"] is True  # informativo: llega en silencio
    # La siguiente versión sí se avisa.
    ultima["tag"] = "v1.2.0"
    await act.comprobar_job(ctx)
    assert ctx.bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_version_mayor_avisa_de_que_no_se_instala_sola(tmp_db, monkeypatch):
    monkeypatch.setattr(act, "__version__", "1.4.0")
    monkeypatch.setattr(act, "ultima_version",
                        AsyncMock(return_value={"tag": "v2.0.0", "url": "https://x"}))
    ctx = _ctx(tmp_db)
    await act.comprobar_job(ctx)
    texto = ctx.bot.send_message.await_args.kwargs["text"]
    assert act.t("act.mayor") in texto and act.t("act.auto") not in texto


@pytest.mark.asyncio
@pytest.mark.parametrize("tag,entorno", [
    ("v1.0.0", None),          # la misma
    ("v0.9.0", None),          # una más vieja (la copia va por main, por delante)
    (None, None),              # no hay ninguna publicada
    ("v1.1.0", "false"),       # UPDATE_CHECK=false
])
async def test_no_avisa(tmp_db, monkeypatch, tag, entorno):
    monkeypatch.setattr(act, "__version__", "1.0.0")
    if entorno:
        monkeypatch.setenv("UPDATE_CHECK", entorno)
    else:
        monkeypatch.delenv("UPDATE_CHECK", raising=False)
    respuesta = {"tag": tag, "url": "https://x"} if tag else None
    monkeypatch.setattr(act, "ultima_version", AsyncMock(return_value=respuesta))
    ctx = _ctx(tmp_db)
    await act.comprobar_job(ctx)
    ctx.bot.send_message.assert_not_awaited()


# ------------------------------------------------------------ tras update.sh

def _pendiente(tmp_path, **datos):
    ruta = tmp_path / "update-pending.json"
    ruta.write_text(json.dumps({"from": "v1.0.0", "to": "v1.1.0", "ts": time.time(), **datos}))
    return ruta


def test_leer_pendiente_lo_borra(tmp_path):
    ruta = _pendiente(tmp_path)
    assert act.leer_pendiente(ruta)["to"] == "v1.1.0"
    assert not ruta.exists()
    assert act.leer_pendiente(ruta) is None


@pytest.mark.parametrize("contenido", [
    "{no es json", json.dumps(["x"]), json.dumps({"to": "v1.1.0", "ts": 0}),  # viejo
    json.dumps({"to": "lo que sea", "ts": time.time()}),
])
def test_leer_pendiente_descarta_lo_raro_y_lo_viejo(tmp_path, contenido):
    ruta = tmp_path / "update-pending.json"
    ruta.write_text(contenido)
    assert act.leer_pendiente(ruta) is None
    assert not ruta.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("corre,clave", [("1.1.0", "act.hecha"), ("1.0.0", "act.fallida")])
async def test_informa_si_se_quedo_la_nueva_o_volvio_atras(tmp_db, tmp_path, monkeypatch,
                                                         corre, clave):
    monkeypatch.setattr(act, "__version__", corre)
    monkeypatch.setattr(act, "PENDIENTE", _pendiente(tmp_path))
    ctx = _ctx(tmp_db)
    await act.informar_job(ctx)
    kw = ctx.bot.send_message.await_args.kwargs
    assert kw["text"].split("<b>")[0] == act.t(clave, nueva="v1.1.0", antes="v1.0.0",
                                               actual=f"v{corre}").split("<b>")[0]
    assert "v1.1.0" in kw["text"]
    # Una sola vez: el fichero ya no está.
    await act.informar_job(ctx)
    ctx.bot.send_message.assert_awaited_once()
