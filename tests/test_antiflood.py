"""Tests para _antiflood_check (threshold graduado por trust)."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.db import DB
from src.handlers import _antiflood_check


@pytest.fixture
def db(tmp_path):
    return DB(str(tmp_path / "t.db"))


def _ctx_for_trust(trust: int):
    """Crea context falso que devuelve trust fijo via _trust_score_cached."""
    bot_data = {"_trust_cache": {(1, 2): (trust, time.time() + 60)}}
    return SimpleNamespace(bot_data=bot_data)


def test_high_trust_disables(db):
    ctx = _ctx_for_trust(95)
    for i in range(20):
        action = _antiflood_check(ctx, db, 1, 2, msg_id=i)
        assert action is None  # trust >= 90 nunca dispara


def test_low_trust_5_msgs_in_10s(db):
    ctx = _ctx_for_trust(20)
    actions = [_antiflood_check(ctx, db, 1, 2, msg_id=i) for i in range(7)]
    assert actions[:4] == [None, None, None, None]
    assert actions[4] == "mute_5m"


def test_medium_trust_8_threshold(db):
    ctx = _ctx_for_trust(50)
    actions = [_antiflood_check(ctx, db, 1, 2, msg_id=i) for i in range(10)]
    # 4 < 8 → None
    assert actions[4] is None
    # 8 msgs → action
    assert actions[7] == "mute_5m"


def test_veteran_12_threshold(db):
    """Trust 70-89 (veteranos): margen amplio de 12 msgs."""
    ctx = _ctx_for_trust(80)
    actions = [_antiflood_check(ctx, db, 1, 2, msg_id=i) for i in range(15)]
    # 8 msgs → None (veterano)
    assert actions[7] is None
    # 12 msgs → action
    assert actions[11] == "mute_5m"


def test_no_double_trigger_within_30s(db):
    """Tras un mute, no se dispara otra vez en 30s."""
    ctx = _ctx_for_trust(20)
    # Disparar el primer mute
    for i in range(5):
        action = _antiflood_check(ctx, db, 1, 2, msg_id=i)
    assert action == "mute_5m"
    # Inmediatamente después: NO debe disparar de nuevo
    for i in range(5, 15):
        action = _antiflood_check(ctx, db, 1, 2, msg_id=i)
    assert action is None  # supresión 30s
