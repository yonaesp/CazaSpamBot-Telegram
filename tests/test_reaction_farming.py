"""Tests del detector reaction_farming."""
from __future__ import annotations

from src.detectors import reaction_farming as rf


def test_no_hit_when_user_has_messages():
    hit = rf.check(user_id=42, total_msgs_user=1, reactions_in_window=10,
                   threshold_count=5, threshold_seconds=60)
    assert not hit


def test_no_hit_below_threshold():
    hit = rf.check(user_id=42, total_msgs_user=0, reactions_in_window=3,
                   threshold_count=5, threshold_seconds=60)
    assert not hit


def test_hit_at_threshold():
    hit = rf.check(user_id=42, total_msgs_user=0, reactions_in_window=5,
                   threshold_count=5, threshold_seconds=60)
    assert hit
    assert hit.score == 100


def test_hit_well_above_threshold():
    hit = rf.check(user_id=42, total_msgs_user=0, reactions_in_window=20,
                   threshold_count=5, threshold_seconds=60)
    assert hit
    assert hit.payload["reactions"] == 20
