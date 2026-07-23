"""Ajuste por chat `money_guard`: modula la agresividad de los detectores de
dinero/trabajo (commercial_ad, investment_scam) en el primer mensaje.

'normal' (defecto): comportamiento de siempre.
'soft': solo caen los casos MUY claros; los borderline de trabajo/dinero pasan.
'off': esos dos detectores no actúan (el resto sigue).
"""
import os
import sqlite3
import tempfile

import pytest

from src.db import DB
from src.detectors import Hit
from src.handlers import _MONEY_SOFT_MIN_SCORE, _apply_money_guard, _chat_money_guard


def _hit(score: int, rule: str = "investment_scam") -> Hit:
    return Hit(rule=rule, score=score, reason="x")


@pytest.mark.parametrize("modo,score,esperado_actua", [
    ("normal", 65, True),    # borderline: en normal sí actúa
    ("normal", 120, True),
    ("soft", 65, False),     # borderline: en suave se deja pasar
    ("soft", 120, True),     # caso claro: en suave sigue actuando
    ("off", 65, False),
    ("off", 120, False),     # off anula incluso el caso claro
])
def test_apply_money_guard(modo, score, esperado_actua):
    r = _apply_money_guard(_hit(score), modo)
    assert bool(r.score >= 60) == esperado_actua


def test_soft_umbral_coherente():
    # El umbral soft debe estar por encima del de los detectores (60).
    assert _MONEY_SOFT_MIN_SCORE > 60
    assert _apply_money_guard(_hit(_MONEY_SOFT_MIN_SCORE), "soft").score >= 60
    assert _apply_money_guard(_hit(_MONEY_SOFT_MIN_SCORE - 1), "soft").score == 0


def test_hit_vacio_no_revienta():
    assert _apply_money_guard(Hit.none(), "soft").score == 0
    assert _apply_money_guard(Hit.none(), "off").score == 0


def test_lectura_a_prueba_de_fallos():
    d = tempfile.mkdtemp()
    db = DB(os.path.join(d, "t.db"))
    db.ensure_chat_settings(-100)
    assert _chat_money_guard(db, -100) == "normal"       # default
    db.update_chat_setting(-100, "money_guard", "soft")
    assert _chat_money_guard(db, -100) == "soft"
    # chat inexistente cae a normal, no revienta
    assert _chat_money_guard(db, -999999) == "normal"

    class Rota:
        def get_chat_settings(self, cid):
            raise RuntimeError("BD ocupada")
    assert _chat_money_guard(Rota(), -1) == "normal"


def test_migracion_blanda_y_default():
    """Una BD vieja sin la columna la gana al abrir, con valor 'normal'."""
    d = tempfile.mkdtemp()
    p = os.path.join(d, "vieja.db")
    # tabla mínima sin money_guard
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE chat_settings (chat_id INTEGER PRIMARY KEY, updated_at REAL NOT NULL DEFAULT 0)")
    c.execute("INSERT INTO chat_settings (chat_id) VALUES (-100)")
    c.commit()
    c.close()
    db = DB(p)  # dispara la migración
    cols = {r[1] for r in sqlite3.connect(p).execute("PRAGMA table_info(chat_settings)")}
    assert "money_guard" in cols
    assert _chat_money_guard(db, -100) == "normal"


def test_money_guard_en_allowed():
    """El campo debe poder editarse desde el panel (estar en ALLOWED)."""
    d = tempfile.mkdtemp()
    db = DB(os.path.join(d, "t.db"))
    db.ensure_chat_settings(-100)
    db.update_chat_setting(-100, "money_guard", "off")  # no debe lanzar
    assert db.get_chat_settings(-100)["money_guard"] == "off"
