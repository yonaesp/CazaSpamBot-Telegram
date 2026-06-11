"""Tests del módulo de scoring."""
from __future__ import annotations

from src.detectors import Hit
from src.scoring import decide


def _h(rule="r", score=50):
    return Hit(rule=rule, score=score, reason="r")


def test_noop_when_no_hits():
    d = decide([], 100, 70, 40, "ban", False)
    assert d.action == "noop"
    assert d.score == 0


def test_ban_at_threshold():
    d = decide([_h(score=100)], 100, 70, 40, "ban", False)
    assert d.action == "ban"


def test_kick_at_threshold():
    d = decide([_h(score=70)], 100, 70, 40, "ban", False)
    assert d.action == "kick"


def test_mute_at_threshold():
    d = decide([_h(score=40)], 100, 70, 40, "ban", False)
    assert d.action == "mute"


def test_delete_below_mute():
    d = decide([_h(score=10)], 100, 70, 40, "ban", False)
    assert d.action == "delete"


def test_score_accumulates():
    d = decide([_h("a", 30), _h("b", 30), _h("c", 50)], 100, 70, 40, "ban", False)
    assert d.score == 110
    assert d.action == "ban"
    assert "a+b+c" == d.rule


def test_first_msg_attack_override_ban():
    d = decide([_h(score=30)], 100, 70, 40, "ban", True)
    assert d.action == "ban"
    assert d.score == 30  # score conservado, acción forzada


def test_first_msg_attack_override_kick():
    d = decide([_h(score=30)], 100, 70, 40, "kick", True)
    assert d.action == "kick"


def test_first_msg_attack_override_mute_24h():
    d = decide([_h(score=30)], 100, 70, 40, "mute_24h", True)
    assert d.action == "mute"


def test_first_msg_attack_shadow_keeps_noop():
    d = decide([_h(score=30)], 100, 70, 40, "shadow", True)
    assert d.action == "noop"
