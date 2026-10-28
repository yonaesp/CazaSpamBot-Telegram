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


# ── Botones «Banear en todos» / «Solo aquí» ─────────────────────────────────

class _Bot:
    """Doble de la Bot API con lo que usan federate_ban y el callback."""

    def __init__(self):
        self.baneos = []

    async def ban_chat_member(self, chat_id, user_id):
        self.baneos.append((chat_id, user_id))

    async def delete_messages(self, chat_id, message_ids):
        return True


class _Query:
    def __init__(self, data, uid):
        self.data = data
        self.from_user = SimpleNamespace(id=uid)
        self.respuestas = []
        self.markup = "sin tocar"

    async def answer(self, texto=None, **k):
        self.respuestas.append(texto)

    async def edit_message_reply_markup(self, reply_markup=None):
        self.markup = reply_markup


def _ctx_cb(db, bot):
    cfg = SimpleNamespace(admin_user_id=1, shadow=False)
    return SimpleNamespace(bot=bot, bot_data={"cfg": cfg, "db": db})


def _alta_chats(db):
    for cid in (-1001, -1002, -1003):
        db.upsert_bot_chat(cid, f"G{cid}", "supergroup", True, True, True)


def test_banear_en_todos_extiende_el_ban_y_lo_registra(tmp_db):
    _alta_chats(tmp_db)
    bot = _Bot()
    q = _Query("mban:all:-1001:5031063111", uid=1)
    asyncio.run(handlers.on_manual_ban_callback(SimpleNamespace(callback_query=q), _ctx_cb(tmp_db, bot)))
    assert sorted(c for c, _ in bot.baneos) == [-1003, -1002, -1001]
    assert tmp_db.is_banned(5031063111)
    assert q.markup != "sin tocar"  # se quitan los botones


def test_solo_aqui_no_banea_nada(tmp_db):
    _alta_chats(tmp_db)
    bot = _Bot()
    q = _Query("mban:here:-1001:5031063111", uid=1)
    asyncio.run(handlers.on_manual_ban_callback(SimpleNamespace(callback_query=q), _ctx_cb(tmp_db, bot)))
    assert bot.baneos == [] and not tmp_db.is_banned(5031063111)


def test_solo_el_dueno_puede_pulsar(tmp_db):
    _alta_chats(tmp_db)
    bot = _Bot()
    q = _Query("mban:all:-1001:5031063111", uid=999)
    asyncio.run(handlers.on_manual_ban_callback(SimpleNamespace(callback_query=q), _ctx_cb(tmp_db, bot)))
    assert bot.baneos == [] and not tmp_db.is_banned(5031063111)


def test_callback_data_cabe_en_64_bytes():
    for b in handlers._botones_ban_manual(-1001008178265, 9999999999):
        assert len(b.callback_data.encode()) <= 64
