"""La antigüedad sin participación no da confianza.

Caso real (26-sep-2026, Windows 11): «Miguel Angel» (8488005572) entró el 24-jun,
no escribió nada en TRES MESES y su primer mensaje fue un reenvío de un bot con
publicidad porno y un botón a una web. `forward_first_msg` puntuó 95 (kick), pero
con 0 mensajes tenía trust 61 —todo por días en el grupo— y el kick se convirtió en
una pregunta al admin, tres veces seguidas; el cuarto mensaje pasó sin preguntar.

Medido sobre las 15 decisiones que el trust ha ablandado: todas las de gente con
≤3 mensajes acabaron en ban; de las de quien participa, ninguna.
"""
from __future__ import annotations

import time

import pytest

from src.db import DB, MIN_MSGS_PARA_ANTIGUEDAD

CHAT = -1001190184646
DIA = 86400


@pytest.fixture
def db(tmp_path):
    return DB(str(tmp_path / "t.db"))


def _persona(db, uid, msgs, dias, join=True):
    ts = time.time() - dias * DIA
    with db._cur() as c:
        c.execute("INSERT INTO seen_users (chat_id, user_id, first_seen_ts, join_ts, msg_count) "
                  "VALUES (?, ?, ?, ?, ?)", (CHAT, uid, ts, ts if join else None, msgs))


def test_el_caso_real_ya_no_llega_a_revision(db):
    """3 meses dentro y su primer mensaje: antes 61, ahora por debajo de 40,
    así que el kick se aplica en vez de preguntar."""
    _persona(db, 8488005572, msgs=1, dias=94)
    assert db.user_trust_score(CHAT, 8488005572) < 40


def test_ni_con_el_segundo_ni_con_el_tercer_mensaje(db):
    for msgs in (2, 3):
        _persona(db, 1000 + msgs, msgs=msgs, dias=94)
        assert db.user_trust_score(CHAT, 1000 + msgs) < 40


def test_quien_participa_conserva_su_antiguedad(db):
    """El veterano de verdad no pierde nada: 20 mensajes y 3 meses sigue ≥70."""
    _persona(db, 2000, msgs=20, dias=94)
    assert db.user_trust_score(CHAT, 2000) >= 70


def test_el_umbral_son_tres_previos_mas_el_actual(db):
    """`msg_count` incluye el mensaje que se está juzgando."""
    assert MIN_MSGS_PARA_ANTIGUEDAD == 4
    _persona(db, 3000, msgs=3, dias=94)
    _persona(db, 3001, msgs=4, dias=94)
    assert db.user_trust_score(CHAT, 3001) - db.user_trust_score(CHAT, 3000) >= 40


def test_el_mensaje_opaco_deja_traza():
    """Sin esa línea no se puede saber qué vio la Bot API de un contenido que
    MTProto da como `MessageMediaUnsupported`."""
    from pathlib import Path
    fuente = Path("src/handlers.py").read_text(encoding="utf-8")
    assert 'log.info("mensaje opaco user=%s' in fuente
    assert "api_kwargs" in fuente
