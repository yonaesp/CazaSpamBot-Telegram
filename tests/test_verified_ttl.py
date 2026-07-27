"""Cuánto dura el mensaje de «verificación correcta» (`verified_ttl_s`).

Al pulsar SOY HUMANO el prompt se EDITA (no se crea un segundo mensaje) y pasa a
ser el saludo. Este ajuste decide cuánto se queda antes de borrarse solo, por
chat, con 0 = no borrarlo nunca.
"""
import sqlite3

import pytest

from src import verification as v
from src.db import DB


def _s(tmp_path, valor=None):
    db = DB(str(tmp_path / "t.db"))
    db.ensure_chat_settings(-100)
    if valor is not None:
        db.update_chat_setting(-100, "verified_ttl_s", valor)
    return db, db.get_chat_settings(-100)


def test_null_hereda_el_env(tmp_path):
    """NULL = «no se ha decidido aquí» -> manda el .env, no un default a ciegas."""
    _, s = _s(tmp_path)
    assert s["verified_ttl_s"] is None
    assert v._verified_ttl(s) == v.VERIFIED_WELCOME_DELETE_AFTER_S


def test_cero_es_nunca_borrar_no_sin_definir(tmp_path):
    """El error fácil aquí es tratar 0 como «vacío» con un `or` y devolver el
    default: 0 es una elección válida del admin (dejarlo para siempre)."""
    _, s = _s(tmp_path, 0)
    assert v._verified_ttl(s) == 0


@pytest.mark.parametrize("valor", [300, 900, 3600])
def test_valor_propio_manda(tmp_path, valor):
    _, s = _s(tmp_path, valor)
    assert v._verified_ttl(s) == valor


def test_valores_corruptos_caen_al_env(tmp_path):
    """Nunca debe reventar por un valor raro en la BD."""
    db = DB(str(tmp_path / "t.db"))
    db.ensure_chat_settings(-100)
    with db._cur() as c:
        c.execute("UPDATE chat_settings SET verified_ttl_s='basura' WHERE chat_id=-100")
    assert v._verified_ttl(db.get_chat_settings(-100)) == v.VERIFIED_WELCOME_DELETE_AFTER_S
    assert v._verified_ttl(None) == v.VERIFIED_WELCOME_DELETE_AFTER_S


def test_negativo_se_normaliza_a_nunca(tmp_path):
    _, s = _s(tmp_path, -5)
    assert v._verified_ttl(s) == 0


def test_default_del_codigo_es_cinco_minutos():
    """Lo que se lleva quien instala el bot desde cero (sin tocar el .env)."""
    import inspect
    fuente = inspect.getsource(v)
    assert '_int_env("VERIFIED_WELCOME_DELETE_AFTER_S", 300)' in fuente


def test_el_barrido_devuelve_verified_at(tmp_path):
    """El barrido por BD necesita distinguir el prompt del mensaje ya verificado,
    porque este último puede tener TTL «nunca». Sin `verified_at` en el SELECT no
    podría, y borraría un mensaje que el admin quiere permanente."""
    db = DB(str(tmp_path / "t.db"))
    filas = db.pending_welcomes_past_ttl(1, 1)
    assert isinstance(filas, list)
    # la consulta debe exponer la columna aunque no haya filas
    with db._cur() as c:
        cols = [d[0] for d in c.execute(
            "SELECT chat_id, user_id, welcome_msg_id, verified_at "
            "FROM pending_verifications LIMIT 0").description]
    assert "verified_at" in cols


def test_migracion_blanda_desde_bd_sin_la_columna(tmp_path):
    p = str(tmp_path / "vieja.db")
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE chat_settings (chat_id INTEGER PRIMARY KEY, updated_at REAL NOT NULL DEFAULT 0)")
    c.execute("INSERT INTO chat_settings (chat_id) VALUES (-100)")
    c.commit()
    c.close()
    db = DB(p)  # dispara la migración
    cols = {r[1] for r in sqlite3.connect(p).execute("PRAGMA table_info(chat_settings)")}
    assert "verified_ttl_s" in cols
    # los chats existentes quedan en NULL: heredan y nadie cambia de comportamiento
    assert db.get_chat_settings(-100)["verified_ttl_s"] is None


def test_editable_desde_el_panel(tmp_path):
    """Debe estar en ALLOWED de update_chat_setting o el panel no podría guardarlo."""
    db = DB(str(tmp_path / "t.db"))
    db.ensure_chat_settings(-100)
    db.update_chat_setting(-100, "verified_ttl_s", 0)  # no debe lanzar
    assert db.get_chat_settings(-100)["verified_ttl_s"] == 0


def test_el_panel_ofrece_nunca_y_cinco_minutos():
    from src import config_panel as cp
    assert 0 in cp._WELCOME_TTL_PRESETS      # nunca
    assert 300 in cp._WELCOME_TTL_PRESETS    # 5 min
