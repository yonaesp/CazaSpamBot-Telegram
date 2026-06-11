"""Tests del detector url_blocklist."""
from __future__ import annotations

from unittest.mock import MagicMock

from telegram import MessageEntity

from src.detectors import url_blocklist as ub


def _mk_msg(text: str, entities: list[MessageEntity]):
    m = MagicMock()
    m.text = text
    m.caption = None
    m.entities = entities
    m.caption_entities = None
    return m


def test_no_urls():
    m = _mk_msg("Hola que tal", [])
    assert not ub.check(m, ["bit.ly"], True)


def test_blocklisted_url():
    text = "Mira esto: https://bit.ly/abc"
    ents = [MessageEntity(type=MessageEntity.URL, offset=11, length=len("https://bit.ly/abc"))]
    m = _mk_msg(text, ents)
    hit = ub.check(m, ["bit.ly", "tinyurl.com"], True)
    assert hit
    assert hit.score == 60
    assert "bit.ly" in hit.reason


def test_non_blocklisted_url():
    text = "https://google.com"
    ents = [MessageEntity(type=MessageEntity.URL, offset=0, length=len(text))]
    m = _mk_msg(text, ents)
    assert not ub.check(m, ["bit.ly"], True)


def test_text_link_blocklisted():
    text = "click aquí"
    ents = [MessageEntity(type=MessageEntity.TEXT_LINK, offset=0, length=5, url="https://goo.gl/xxx")]
    m = _mk_msg(text, ents)
    hit = ub.check(m, ["goo.gl"], True)
    assert hit


def test_subdomain_matches_blocklist():
    text = "https://x.bit.ly/abc"
    ents = [MessageEntity(type=MessageEntity.URL, offset=0, length=len(text))]
    m = _mk_msg(text, ents)
    hit = ub.check(m, ["bit.ly"], True)
    assert hit


def test_lower_score_when_not_first():
    text = "https://bit.ly/x"
    ents = [MessageEntity(type=MessageEntity.URL, offset=0, length=len(text))]
    m = _mk_msg(text, ents)
    hit = ub.check(m, ["bit.ly"], False)
    assert hit.score == 25
