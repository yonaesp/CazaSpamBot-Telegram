"""Tests del bridge Telethon: normalización de chat_id a formato Bot API."""
from __future__ import annotations

from src.telethon_bridge import _marked_chat_id


def test_id_crudo_positivo_se_marca():
    """Telethon antiguo da el id de canal en crudo (positivo) → se antepone -100."""
    assert _marked_chat_id(1156069668) == -1001156069668


def test_id_ya_marcado_se_deja_igual():
    """Telethon moderno (1.43) ya da el id marcado y negativo → idempotente."""
    assert _marked_chat_id(-1001156069668) == -1001156069668


def test_idempotencia_doble_llamada():
    """Aplicarlo dos veces no corrompe el id (no re-marca)."""
    once = _marked_chat_id(1008178265)
    assert _marked_chat_id(once) == once == -1001008178265


def test_los_tres_grupos_reales():
    """Los 3 supergrupos reales, en cualquiera de las dos formas, mapean igual."""
    for raw, marked in [
        (1156069668, -1001156069668),
        (1190184646, -1001190184646),
        (1008178265, -1001008178265),
    ]:
        assert _marked_chat_id(raw) == marked
        assert _marked_chat_id(marked) == marked
