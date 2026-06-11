"""Tests para db.user_trust_score (gradiente 0-100)."""
from __future__ import annotations

import time

import pytest

from src.db import DB


@pytest.fixture
def db(tmp_path):
    return DB(str(tmp_path / "test.db"))


def _seed_seen(db: DB, chat_id: int, user_id: int, msg_count: int = 0,
               first_seen_offset_days: float | None = None,
               join_ts_offset_days: float | None = None,
               whitelisted: int = 0, first_name: str = "Test"):
    now = time.time()
    first_seen_ts = now - (first_seen_offset_days or 0) * 86400 if first_seen_offset_days is not None else now
    join_ts = now - (join_ts_offset_days * 86400) if join_ts_offset_days is not None else None
    with db._cur() as c:
        c.execute(
            "INSERT OR REPLACE INTO seen_users (chat_id, user_id, username, first_seen_ts, "
            "join_ts, msg_count, whitelisted, first_name) VALUES (?,?,?,?,?,?,?,?)",
            (chat_id, user_id, "u", first_seen_ts, join_ts, msg_count, whitelisted, first_name),
        )


def test_unknown_user_is_zero(db):
    assert db.user_trust_score(-100, 999) == 0


def test_whitelisted_user_is_100(db):
    _seed_seen(db, -100, 1, msg_count=0, whitelisted=1)
    assert db.user_trust_score(-100, 1) == 100


def test_brand_new_user_low_score(db):
    """User que acaba de aparecer con 1 mensaje: score muy bajo."""
    _seed_seen(db, -100, 1, msg_count=1, first_seen_offset_days=0.01)
    score = db.user_trust_score(-100, 1)
    assert score < 10


def test_active_recent_user_medium_score(db):
    """User con 15 mensajes y 5 días en grupo + join visto."""
    _seed_seen(db, -100, 1, msg_count=15, first_seen_offset_days=5, join_ts_offset_days=5)
    score = db.user_trust_score(-100, 1)
    # 15 msgs (15) + 5 días * 1.5 (7.5) + join (10) = ~32-33
    assert 25 <= score <= 40


def test_veteran_user_high_score(db):
    """Veterano: 50 msgs, 60 días, join visto. Debe pasar el umbral de skip (70)."""
    _seed_seen(db, -100, 1, msg_count=50, first_seen_offset_days=60, join_ts_offset_days=60)
    score = db.user_trust_score(-100, 1)
    # 40 (msgs cap) + 30 (days cap) + 20 (>=30d) + 10 (join) = 100
    assert score >= 70


def test_pre_existing_no_join_still_gets_score(db):
    """User pre-existente al bot: join_ts=NULL, pero msg_count + days deben dar score decente."""
    _seed_seen(db, -100, 1, msg_count=30, first_seen_offset_days=45, join_ts_offset_days=None)
    score = db.user_trust_score(-100, 1)
    # 30 (msgs) + 30 (days cap) + 20 (>=30d) - 0 = 80, sin los +10 de join
    assert score >= 70


def test_warns_reduce_score(db):
    _seed_seen(db, -100, 1, msg_count=30, first_seen_offset_days=45, join_ts_offset_days=45)
    base = db.user_trust_score(-100, 1)
    with db._cur() as c:
        c.execute(
            "INSERT INTO user_warns (user_id, chat_id, by_admin, reason, ts) VALUES (?,?,?,?,?)",
            (1, -100, 99, "test warn", time.time()),
        )
    after = db.user_trust_score(-100, 1)
    assert after == base - 10


def test_score_capped_at_100(db):
    _seed_seen(db, -100, 1, msg_count=999, first_seen_offset_days=9999, join_ts_offset_days=9999)
    assert db.user_trust_score(-100, 1) == 100


def test_score_capped_at_zero(db):
    """Con muchos warns el score se queda en 0, no negativo."""
    _seed_seen(db, -100, 1, msg_count=1, first_seen_offset_days=1)
    with db._cur() as c:
        for _ in range(10):
            c.execute(
                "INSERT INTO user_warns (user_id, chat_id, by_admin, reason, ts) VALUES (?,?,?,?,?)",
                (1, -100, 99, "warn", time.time()),
            )
    assert db.user_trust_score(-100, 1) == 0
