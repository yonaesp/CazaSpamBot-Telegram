"""Tests del bridge Telethon: normalización de chat_id a formato Bot API.

Los chat_id de aquí son INVENTADOS (solo importa la transformación numérica).
"""
from __future__ import annotations

from src.telethon_bridge import _marked_chat_id


def test_id_crudo_positivo_se_marca():
    """Telethon antiguo da el id de canal en crudo (positivo) → se antepone -100."""
    assert _marked_chat_id(1234567890) == -1001234567890


def test_id_ya_marcado_se_deja_igual():
    """Telethon moderno (1.43) ya da el id marcado y negativo → idempotente."""
    assert _marked_chat_id(-1001234567890) == -1001234567890


def test_idempotencia_doble_llamada():
    """Aplicarlo dos veces no corrompe el id (no re-marca)."""
    once = _marked_chat_id(1234500055)
    assert _marked_chat_id(once) == once == -1001234500055


def test_varios_grupos_de_ejemplo():
    """Varios chat_id de ejemplo, en cualquiera de las dos formas, mapean igual."""
    for raw, marked in [
        (1234567890, -1001234567890),
        (1234500001, -1001234500001),
        (1234500002, -1001234500002),
    ]:
        assert _marked_chat_id(raw) == marked
        assert _marked_chat_id(marked) == marked
