"""Tests para detector forward_first_msg."""
from __future__ import annotations

from types import SimpleNamespace

from src.detectors import forward_first_msg as det


def _msg(forward_from_chat=None, forward_from=None, forward_sender_name=None, forward_origin=None):
    return SimpleNamespace(
        forward_from_chat=forward_from_chat,
        forward_from=forward_from,
        forward_sender_name=forward_sender_name,
        forward_origin=forward_origin,
    )


def test_no_forward_returns_none():
    hit = det.check(_msg(), is_first_msg=True)
    assert hit is None or hit.score == 0


def test_not_first_msg_outside_window_returns_none():
    fwd_chat = SimpleNamespace(type="channel", username="spamchan", title="Spam")
    hit = det.check(_msg(forward_from_chat=fwd_chat), is_first_msg=False, seconds_since_first_seen=600)
    assert hit is None or hit.score == 0


def test_forward_from_channel_first_msg_bans():
    fwd_chat = SimpleNamespace(type="channel", username="飞哥收款赚几千", title="飞哥收款赚几千")
    hit = det.check(_msg(forward_from_chat=fwd_chat), is_first_msg=True)
    assert hit is not None
    assert hit.rule == "forward_first_msg"
    assert hit.score == 100
    assert "CANAL" in hit.reason
    assert hit.payload["origin_type"] == "channel"


def test_forward_from_bot_first_msg_bans():
    fwd_user = SimpleNamespace(is_bot=True, username="spambot", first_name="SpamBot")
    hit = det.check(_msg(forward_from=fwd_user), is_first_msg=True)
    assert hit is not None
    assert hit.score == 95
    assert hit.payload["origin_type"] == "bot"


def test_forward_from_user_first_msg_kicks():
    fwd_user = SimpleNamespace(is_bot=False, username="someone", first_name="Someone")
    hit = det.check(_msg(forward_from=fwd_user), is_first_msg=True)
    assert hit is not None
    assert hit.score == 80


def test_forward_in_early_window_after_first_msg():
    fwd_chat = SimpleNamespace(type="channel", username="x", title="x")
    # is_first_msg=False pero dentro de 3 min
    hit = det.check(_msg(forward_from_chat=fwd_chat), is_first_msg=False, seconds_since_first_seen=100)
    assert hit is not None
    assert hit.score >= 70


def test_forward_hidden_user():
    hit = det.check(_msg(forward_sender_name="Anonimo"), is_first_msg=True)
    assert hit is not None
    assert hit.payload["origin_type"] == "hidden_user"
    assert hit.score == 80


def test_forward_origin_ptb21_channel():
    """PTB ≥21 usa forward_origin con type='channel'."""
    chat = SimpleNamespace(username="evilch", title="EvilChan")
    origin = SimpleNamespace(type="channel", chat=chat)
    hit = det.check(_msg(forward_origin=origin), is_first_msg=True)
    assert hit is not None
    assert hit.score == 100
    assert hit.payload["origin_type"] == "channel"
    assert hit.payload["origin_name"] == "evilch"
