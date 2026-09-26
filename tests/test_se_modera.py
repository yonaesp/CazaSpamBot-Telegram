"""Solo se modera donde el bot puede actuar.

Caso real (25/26-sep-2026): alguien metió el bot como MIEMBRO NORMAL en dos grupos
de pesca ajenos. Con `MODERATED_CHAT_IDS` vacío, `is_moderated` decía que sí a
cualquier chat: allí decidía «ban», avisaba al admin de un «Baneado (sincronizado en
todos los grupos)» que no había podido ejecutar, el spammer seguía dentro, volvía a
escribir cada ~4 h y llegaba otro aviso idéntico. Y los bans entraban en la
federación, así que un grupo ajeno podía banear gente en los propios.
"""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import handlers
from src.db import DB

PROPIO, AJENO = -1001190184646, -1002067804909


@pytest.fixture
def db(tmp_path):
    d = DB(str(tmp_path / "t.db"))
    with d._cur() as c:
        for cid, admin, restr in ((PROPIO, 1, 1), (AJENO, 0, 0), (-100555, 1, 0)):
            c.execute("INSERT INTO bot_chats (chat_id, title, type, am_admin, can_restrict, "
                      "can_delete, added_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                      (cid, "t", "supergroup", admin, restr, admin, time.time(), time.time()))
    return d


def _cfg(lista=()):
    s = set(lista)
    return SimpleNamespace(moderated_chat_ids_set=s,
                           is_moderated=lambda cid: (not s) or cid in s)


def test_el_grupo_ajeno_sin_permisos_no_se_modera(db):
    assert handlers._se_modera(db, _cfg(), AJENO) is False


def test_los_propios_si(db):
    assert handlers._se_modera(db, _cfg(), PROPIO) is True


def test_admin_sin_poder_restringir_tampoco(db):
    """Admin sin permiso de banear: el aviso de «Baneado» volvería a mentir."""
    assert handlers._se_modera(db, _cfg(), -100555) is False


def test_un_chat_que_no_conoce_no_se_modera(db):
    assert handlers._se_modera(db, _cfg(), -100999) is False


def test_con_lista_explicita_se_respeta(db):
    """Quien escribe MODERATED_CHAT_IDS sabe lo que pone."""
    assert handlers._se_modera(db, _cfg([AJENO]), AJENO) is True
    assert handlers._se_modera(db, _cfg([AJENO]), PROPIO) is False


def test_las_cuatro_puertas_usan_la_comprobacion_nueva():
    """join, mensaje, reacción y canal: si una sigue con `cfg.is_moderated` a pelo,
    por ahí vuelve a entrar el grupo ajeno."""
    fuente = Path("src/handlers.py").read_text(encoding="utf-8")
    assert fuente.count("if not _se_modera(db, cfg, ") == 4
    assert "if not cfg.is_moderated(" not in fuente.replace(
        "    if not cfg.is_moderated(chat_id):\n        return False", "")
