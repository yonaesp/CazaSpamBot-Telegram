"""El cliente Telethon (bio/fotos/admin_log) debe estar disponible aunque los
reportes de spam estén desactivados. Reportar es un opt-in SEPARADo por el riesgo
a la cuenta secundaria; no debe apagar el resto de funciones Telethon.
"""
from __future__ import annotations

from src.reporter import SpamReporter

_SENTINEL = object()  # hace de "cliente conectado"


def _reporter(telethon: bool, reporting: bool, connected: bool) -> SpamReporter:
    r = SpamReporter(telethon_enabled=telethon, reporting_enabled=reporting)
    r._client = _SENTINEL if connected else None
    return r


def test_telethon_sin_reportes_mantiene_cliente():
    """telethon ON + reportes OFF + conectado → cliente disponible, pero no reporta."""
    r = _reporter(telethon=True, reporting=False, connected=True)
    assert r.is_ready() is True            # bio/fotos/admin_log/bridge SÍ
    assert r.get_client() is _SENTINEL
    assert r.reporting_ready() is False    # reportes NO
    r.enqueue(chat_id=1, user_id=2, message_id=3, reason="spam", detail="x")
    assert r._queue.qsize() == 0           # no encola nada


def test_telethon_con_reportes_encola():
    r = _reporter(telethon=True, reporting=True, connected=True)
    assert r.is_ready() is True
    assert r.reporting_ready() is True
    r.enqueue(chat_id=1, user_id=2, message_id=3, reason="spam", detail="x")
    assert r._queue.qsize() == 1


def test_telethon_off_nada_disponible():
    """Sin Telethon, ni cliente ni reportes, aunque reporting_enabled sea True."""
    r = _reporter(telethon=False, reporting=True, connected=False)
    assert r.is_ready() is False
    assert r.get_client() is None
    assert r.reporting_ready() is False


def test_telethon_on_pero_no_conectado():
    """telethon ON pero sesión/credenciales fallan (client None) → nada disponible."""
    r = _reporter(telethon=True, reporting=True, connected=False)
    assert r.is_ready() is False
    assert r.get_client() is None
    assert r.reporting_ready() is False
