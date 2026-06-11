"""Tests para detector inline_buttons (users normales no pueden enviar reply_markup)."""
from __future__ import annotations

from types import SimpleNamespace

from src.detectors import inline_buttons as det


def _msg(reply_markup=None):
    return SimpleNamespace(reply_markup=reply_markup)


def _markup(rows):
    return SimpleNamespace(inline_keyboard=rows)


def _btn(text, url=None, callback_data=None):
    return SimpleNamespace(text=text, url=url, callback_data=callback_data)


def test_no_reply_markup_returns_none():
    hit = det.check(_msg())
    assert hit is None or hit.score == 0


def test_empty_keyboard_returns_none():
    hit = det.check(_msg(reply_markup=_markup([])))
    assert hit is None or hit.score == 0


def test_single_button_with_url_triggers():
    rm = _markup([[_btn("Join", url="https://t.me/spamchan")]])
    hit = det.check(_msg(reply_markup=rm))
    assert hit is not None
    assert hit.rule == "inline_buttons_from_user"
    assert hit.score == 90
    assert hit.payload["n_buttons"] == 1
    assert "https://t.me/spamchan" in hit.payload["urls"]


def test_multiple_buttons_count():
    rm = _markup([
        [_btn("a", url="https://x.com"), _btn("b", callback_data="cb")],
        [_btn("c", url="https://y.com")],
    ])
    hit = det.check(_msg(reply_markup=rm))
    assert hit is not None
    assert hit.payload["n_buttons"] == 3
    assert len(hit.payload["urls"]) == 2


def test_callback_data_only_no_urls():
    rm = _markup([[_btn("verify", callback_data="verify:123")]])
    hit = det.check(_msg(reply_markup=rm))
    assert hit is not None
    assert hit.payload["n_buttons"] == 1
    assert hit.payload["urls"] == []
