"""Tests del detector external_mention."""
from __future__ import annotations

from unittest.mock import MagicMock

from telegram import MessageEntity, User

from src.detectors import external_mention as em


def _mk_msg(text: str, entities: list[MessageEntity]):
    m = MagicMock()
    m.text = text
    m.caption = None
    m.entities = entities
    m.caption_entities = None
    return m


def test_no_mentions_no_hit():
    m = _mk_msg("Hola mundo", [])
    hit = em.check(m, -100, True, True, True,
                   is_user_in_chat=lambda c, u: False,
                   resolve_username=lambda h: None)
    assert not hit


def test_external_mention_first_msg_with_spanish_context():
    """Con texto en español que acompaña la mención → score 60 (sospechoso pero no ban directo)."""
    text = "Hola @externo, ¿cómo estás?"
    ents = [MessageEntity(type=MessageEntity.MENTION, offset=5, length=8)]
    m = _mk_msg(text, ents)
    hit = em.check(m, -100, True, True, True,
                   is_user_in_chat=lambda c, u: False,
                   resolve_username=lambda h: None)
    assert hit
    assert hit.score == 60


def test_external_mention_first_msg_no_context_score_ban():
    """Mención sin texto extra → ban directo (score 130)."""
    text = "@externo"
    ents = [MessageEntity(type=MessageEntity.MENTION, offset=0, length=8)]
    m = _mk_msg(text, ents)
    hit = em.check(m, -100, True, True, True,
                   is_user_in_chat=lambda c, u: False,
                   resolve_username=lambda h: None)
    assert hit
    assert hit.score == 130


def test_external_mention_first_msg_non_spanish_text_score_ban():
    """Mención + texto no español → ban directo (score 130)."""
    text = "@externo check this out bro"
    ents = [MessageEntity(type=MessageEntity.MENTION, offset=0, length=8)]
    m = _mk_msg(text, ents)
    hit = em.check(m, -100, True, True, True,
                   is_user_in_chat=lambda c, u: False,
                   resolve_username=lambda h: None)
    assert hit
    assert hit.score == 130


def test_internal_mention_no_hit():
    text = "Hola @amigo"
    ents = [MessageEntity(type=MessageEntity.MENTION, offset=5, length=6)]
    m = _mk_msg(text, ents)
    hit = em.check(m, -100, True, True, True,
                   is_user_in_chat=lambda c, u: u == 42,
                   resolve_username=lambda h: 42)
    assert not hit


def test_text_mention_external():
    """Mención sin texto extra (la "Hola" se consume como entity) → ban directo."""
    user = User(id=999, is_bot=False, first_name="X")
    text = "Hola"
    ents = [MessageEntity(type=MessageEntity.TEXT_MENTION, offset=0, length=4, user=user)]
    m = _mk_msg(text, ents)
    hit = em.check(m, -100, True, True, True,
                   is_user_in_chat=lambda c, u: False,
                   resolve_username=lambda h: None)
    assert hit
    assert "sin contexto" in hit.reason.lower() or "no español" in hit.reason.lower()


def test_external_tg_link():
    text = "Únete https://t.me/otrochat"
    ents = [MessageEntity(type=MessageEntity.URL, offset=6, length=len("https://t.me/otrochat"))]
    m = _mk_msg(text, ents)
    hit = em.check(m, -100, True, True, True,
                   is_user_in_chat=lambda c, u: False,
                   resolve_username=lambda h: None)
    assert hit
    assert hit.score == 100


def test_tg_link_disabled():
    text = "Únete https://t.me/otrochat"
    ents = [MessageEntity(type=MessageEntity.URL, offset=6, length=len("https://t.me/otrochat"))]
    m = _mk_msg(text, ents)
    hit = em.check(m, -100, True, True, False,  # detect_tg_links=False
                   is_user_in_chat=lambda c, u: False,
                   resolve_username=lambda h: None)
    assert not hit


def test_lower_score_not_first_msg():
    text = "Hola @externo"
    ents = [MessageEntity(type=MessageEntity.MENTION, offset=5, length=8)]
    m = _mk_msg(text, ents)
    hit = em.check(m, -100, False, True, True,
                   is_user_in_chat=lambda c, u: False,
                   resolve_username=lambda h: None)
    assert hit.score == 40
