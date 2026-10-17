"""El asistente de instalación deja un `.env` que arranca, sin abrirlo a mano.

17-oct-2026: el README pasó a ser de copiar y pegar, y el único paso que obligaba a
editar el `.env` era la cuenta secundaria (MTProto). Ahora la pregunta el propio
asistente, opcional. Los valores de aquí son inventados.
"""
import builtins

import pytest

import scripts.setup as asistente

TOKEN = "8123456789:AAF-EsteTokenEsFalsoReemplazaloPorElTuyo00"


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    plantilla = tmp_path / ".env.example"
    plantilla.write_text(
        "TELEGRAM_BOT_TOKEN=\nADMIN_USER_ID=\nMODERATED_CHAT_IDS=\n"
        "ADMIN_NOTIFY_CHAT_ID=\nMODE=shadow\nTELETHON_ENABLED=true\n"
        "TG_API_ID=\nTG_API_HASH=\nTG_PHONE=\n")
    monkeypatch.setattr(asistente, "EXAMPLE", plantilla)
    monkeypatch.setattr(asistente, "ENV", tmp_path / ".env")
    monkeypatch.setattr(asistente.sys, "argv", ["setup.py"])
    return tmp_path / ".env"


def _respuestas(monkeypatch, valores):
    pendientes = iter(valores)

    def falso_input(_prompt=""):
        try:
            return next(pendientes)
        except StopIteration:
            raise EOFError from None
    monkeypatch.setattr(builtins, "input", falso_input)


def _vars(env):
    return dict(lin.split("=", 1) for lin in env.read_text().splitlines() if "=" in lin)


def test_con_cuenta_secundaria(entorno, monkeypatch):
    _respuestas(monkeypatch, [TOKEN, "123456789", "", "", "shadow",
                              "s", "1234567", "0123456789abcdef0123456789abcdef",
                              "+34600111222"])
    assert asistente.main() == 0
    v = _vars(entorno)
    assert v["TELEGRAM_BOT_TOKEN"] == TOKEN
    assert v["TG_API_ID"] == "1234567"
    assert v["TG_API_HASH"] == "0123456789abcdef0123456789abcdef"
    assert v["TG_PHONE"] == "+34600111222"


def test_sin_cuenta_secundaria(entorno, monkeypatch):
    _respuestas(monkeypatch, [TOKEN, "123456789", "", "", "active", ""])
    assert asistente.main() == 0
    v = _vars(entorno)
    assert v["MODE"] == "active"
    assert v["TG_API_ID"] == "" and v["TG_PHONE"] == ""


def test_sin_terminal_se_salta_lo_opcional(entorno, monkeypatch):
    """Lo obligatorio llega; a partir de ahí, sin nadie al otro lado, todo lo
    opcional toma su valor por defecto en vez de colgarse."""
    _respuestas(monkeypatch, [TOKEN, "123456789"])
    assert asistente.main() == 0
    v = _vars(entorno)
    assert v["MODE"] == "shadow" and v["TG_API_ID"] == ""


def test_el_env_queda_en_600(entorno, monkeypatch):
    """Lleva el token del bot: legible por cualquiera fue un hallazgo del 9-oct."""
    _respuestas(monkeypatch, [TOKEN, "123456789", "", "", "shadow", ""])
    asistente.main()
    assert entorno.stat().st_mode & 0o777 == 0o600


def test_un_api_hash_mal_copiado_se_vuelve_a_pedir(entorno, monkeypatch):
    _respuestas(monkeypatch, [TOKEN, "123456789", "", "", "shadow", "s", "1234567",
                              "no-es-un-hash", "n",
                              "0123456789abcdef0123456789abcdef", "+34600111222"])
    assert asistente.main() == 0
    assert _vars(entorno)["TG_API_HASH"] == "0123456789abcdef0123456789abcdef"
