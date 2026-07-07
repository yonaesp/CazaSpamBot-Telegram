"""Tests del contenido del welcome reutilizable (_build_welcome_content).

Se usa tanto para el welcome de confianza alta como para el mensaje editado tras
pulsar SOY HUMANO (verificación correcta).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src import verification as v


def _db_sin_botones():
    db = MagicMock()
    db.list_welcome_buttons.return_value = []
    return db


def test_verified_incluye_cabecera_y_nombre_y_footer():
    text, kb = v._build_welcome_content(_db_sin_botones(), -100123, "@juan", verified=True)
    assert "Verificación correcta" in text
    assert "@juan" in text
    assert v._WELCOME_FIXED_FOOTER in text
    assert kb is None  # sin botones configurados en el chat


def test_no_verified_sin_cabecera():
    text, _ = v._build_welcome_content(_db_sin_botones(), -100123, "@ana", verified=False)
    assert "Verificación correcta" not in text
    assert "@ana" in text


def test_incluye_botones_configurados_del_chat():
    db = MagicMock()
    db.list_welcome_buttons.return_value = [
        {"text": "📌 Anclado", "url": "https://t.me/x/1", "same_row": False},
    ]
    _, kb = v._build_welcome_content(db, -100123, "@juan", verified=True)
    assert kb is not None
    assert kb.inline_keyboard[0][0].text == "📌 Anclado"


def test_duracion_configurable_por_defecto_generosa():
    """El welcome verificado dura más que el prompt (para dar tiempo a leer)."""
    assert v.VERIFIED_WELCOME_DELETE_AFTER_S >= 600
