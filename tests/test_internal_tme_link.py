"""Tests de enlaces t.me/ internos (mismo grupo) vs externos."""
from __future__ import annotations

from unittest.mock import MagicMock

from telegram import MessageEntity

from src.detectors import external_mention as em


def _mk_msg(text: str, entities: list[MessageEntity]):
    m = MagicMock()
    m.text = text
    m.caption = None
    m.entities = entities
    m.caption_entities = None
    return m


def test_internal_tme_link_not_external():
    """t.me/MiGrupo/123 desde grupo @MiGrupo → NO se detecta como externo."""
    text = "Mira https://t.me/MiGrupo/348625"
    ents = [MessageEntity(type=MessageEntity.URL, offset=5, length=len("https://t.me/MiGrupo/348625"))]
    m = _mk_msg(text, ents)
    out = em.find_external_telegram_links(m, own_chat_username="MiGrupo")
    assert out == []


def test_external_tme_link_other_chat():
    """t.me/OtroChat/123 sí es externo."""
    text = "Mira https://t.me/OtroChat/100"
    ents = [MessageEntity(type=MessageEntity.URL, offset=5, length=len("https://t.me/OtroChat/100"))]
    m = _mk_msg(text, ents)
    out = em.find_external_telegram_links(m, own_chat_username="MiGrupo")
    assert len(out) == 1


def test_no_own_username_treats_all_as_external():
    text = "Mira https://t.me/MiGrupo/348625"
    ents = [MessageEntity(type=MessageEntity.URL, offset=5, length=len("https://t.me/MiGrupo/348625"))]
    m = _mk_msg(text, ents)
    out = em.find_external_telegram_links(m, own_chat_username=None)
    assert len(out) == 1


def test_username_case_insensitive():
    text = "Mira https://t.me/migrupo/12"
    ents = [MessageEntity(type=MessageEntity.URL, offset=5, length=len("https://t.me/migrupo/12"))]
    m = _mk_msg(text, ents)
    out = em.find_external_telegram_links(m, own_chat_username="MiGrupo")
    assert out == []
