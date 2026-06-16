"""Tests del antiflood (6/60s, mute 6h, revisión humana)."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from src.db import DB
from src.handlers import _antiflood_check


@pytest.fixture
def db(tmp_path):
    return DB(str(tmp_path / "t.db"))


def _ctx_for_trust(trust: int):
    """Context falso con trust fijo (vía _trust_cache) y bot_data vacío para flood."""
    bot_data = {"_trust_cache": {(1, 2): (trust, time.time() + 60)}}
    return SimpleNamespace(bot_data=bot_data)


def test_base_threshold_6(db):
    """Usuario normal: 6 mensajes en la ventana disparan."""
    ctx = _ctx_for_trust(20)
    res = [_antiflood_check(ctx, db, 1, 2) for _ in range(7)]
    assert res[:5] == [False] * 5   # 1..5 mensajes < 6
    assert res[5] is True           # el 6º dispara


def test_veteran_threshold_10(db):
    """Veterano (trust>=70): más margen, 10 mensajes."""
    ctx = _ctx_for_trust(80)
    res = [_antiflood_check(ctx, db, 1, 2) for _ in range(12)]
    assert res[5] is False          # 6 < 10
    assert res[9] is True           # el 10º dispara


def test_human_confirmed_threshold_12(db):
    """Marcado 'no es bot' por el admin: aún más margen, 12 mensajes."""
    db.flood_confirm_human(1, 2)
    ctx = _ctx_for_trust(20)
    res = [_antiflood_check(ctx, db, 1, 2) for _ in range(14)]
    assert res[9] is False          # 10 < 12
    assert res[11] is True          # el 12º dispara (sigue muteándose si reincide)


def test_no_double_trigger_within_60s(db):
    """Tras disparar, no se repite en el mismo burst (60s)."""
    ctx = _ctx_for_trust(20)
    res = [_antiflood_check(ctx, db, 1, 2) for _ in range(6)]
    assert res[5] is True
    again = [_antiflood_check(ctx, db, 1, 2) for _ in range(10)]
    assert all(x is False for x in again)


# ---------- capa DB ----------

def test_flood_record_mute_cuenta(db):
    c1, review1, human1 = db.flood_record_mute(1, 2, time.time())
    assert (c1, review1, human1) == (1, False, False)
    c2, _, _ = db.flood_record_mute(1, 2, time.time())
    assert c2 == 2  # reincidencia acumula


def test_flood_confirm_human(db):
    assert db.flood_is_human_confirmed(1, 2) is False
    db.flood_confirm_human(1, 2)
    assert db.flood_is_human_confirmed(1, 2) is True
    # confirmar humano marca review como enviado (no se vuelve a preguntar)
    _, review, human = db.flood_record_mute(1, 2, time.time())
    assert review is True and human is True


def test_flood_mark_review_sent(db):
    db.flood_record_mute(1, 2, time.time())
    db.flood_mark_review_sent(1, 2)
    _, review, _ = db.flood_record_mute(1, 2, time.time())
    assert review is True
