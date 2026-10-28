"""El aviso de un ban manual enseña cómo era el perfil en ese momento.

Caso real (28-oct-2026): Charlotte, baneada a mano sin escribir nada. El aviso no
dejaba ver por qué y, tras el ban, la mención por id ya no abre el perfil.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

from src import handlers, user_signals


class _Reporter:
    def __init__(self, client):
        self._c = client

    def get_client(self):
        return self._c


def _ctx(client):
    return SimpleNamespace(bot_data={"reporter": _Reporter(client)})


def _target():
    return SimpleNamespace(id=5031063111, first_name="Charlotte", username=None)


def test_perfil_con_bio_de_spam_lo_dice(monkeypatch):
    sig = user_signals.UserSignals(
        user_id=5031063111, photo_count=4,
        oldest_photo=dt.datetime(2022, 1, 7, tzinfo=dt.timezone.utc),
        newest_photo=dt.datetime(2022, 1, 7, tzinfo=dt.timezone.utc),
        bio="Reels are ready when you are — stake1036.com/?c=tg",
        personal_channel_title="Canal <raro>",
    )

    async def fetch(client, user_id, chat_id=None, first_name=None):
        assert user_id == 5031063111 and first_name == "Charlotte"
        return sig

    monkeypatch.setattr(user_signals, "fetch", fetch)
    txt = asyncio.run(handlers._perfil_para_aviso(_ctx(object()), _target(), -100))
    assert "stake1036.com" in txt
    assert "Canal &lt;raro&gt;" in txt
    assert "campaña" in txt or "campaign" in txt


def test_sin_telethon_no_añade_nada():
    assert asyncio.run(handlers._perfil_para_aviso(_ctx(None), _target(), -100)) == ""


def test_si_no_se_puede_leer_lo_dice(monkeypatch):
    async def fetch(*a, **k):
        return None

    monkeypatch.setattr(user_signals, "fetch", fetch)
    txt = asyncio.run(handlers._perfil_para_aviso(_ctx(object()), _target(), -100))
    assert txt.strip()


def test_la_plantilla_tiene_hueco_para_el_perfil():
    for lang in ("es", "en"):
        d = json.loads(Path(f"src/locales/{lang}.json").read_text())
        assert "{perfil}" in d["hdl.manual_ban_alert"]
