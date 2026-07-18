"""Tests del contenido del welcome reutilizable (_build_welcome_content).

Se usa tanto para el welcome de confianza alta como para el mensaje editado tras
pulsar SOY HUMANO (verificación correcta).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src import verification as v
from src.i18n import t


def _db_sin_botones():
    db = MagicMock()
    db.list_welcome_buttons.return_value = []
    return db


def test_verified_incluye_cabecera_y_nombre_y_footer():
    text, kb = v._build_welcome_content(_db_sin_botones(), -100123, "@juan", verified=True)
    assert "Verificación correcta" in text
    assert "@juan" in text
    assert t("welcome.footer_fixed") in text
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


def test_verification_footer_tiempos():
    from src.verification import _verification_footer
    s = {"verification_suspicious_kick_minutes": 30, "verification_kick_normal": 1,
         "verification_reminder_hours": 3, "verification_kick_after_reminder_hours": 6}
    assert "30 min" in _verification_footer(s, True, [(v.REASON_NO_PHOTO, {})])  # sospechoso
    assert "9h" in _verification_footer(s, False, [])                     # normal kick: 3+6
    s2 = dict(s)
    s2["verification_kick_normal"] = 0
    assert "no podrás escribir" in _verification_footer(s2, False, [])    # normal mute
    # NO duplica la instrucción del botón (esa va en el welcome)
    assert "Pulsa el botón" not in _verification_footer(s, True, [])
