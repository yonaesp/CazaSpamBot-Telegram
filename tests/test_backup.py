"""Copia de seguridad consistente de la BD (`maintenance.backup_database`).

Por qué existe: en modo WAL el fichero `.db` puede pasar DÍAS sin recibir un
checkpoint, así que copiarlo a pelo da una foto vieja (medido en produccion: 5
baneos y 20 registros de auditoria de menos), y copiarlo mientras el bot escribe
puede dar además una foto inconsistente. `VACUUM INTO` resuelve las dos cosas.
"""
import sqlite3
import threading
import time
from pathlib import Path

from src.db import DB
from src.maintenance import BACKUP_KEEP, backup_database


def _db_con_datos(tmp_path: Path) -> DB:
    db = DB(str(tmp_path / "antispam.db"))
    db.upsert_bot_chat(-100, "G", "supergroup", True, True, True)
    db.ensure_chat_settings(-100)
    for i in range(50):
        db.log_action(chat_id=-100, user_id=i, username=f"u{i}", message_id=i,
                      rule="test", action="noop", score=1, mode="active", payload=None)
    return db


def test_copia_incluye_lo_que_vive_en_el_wal(tmp_path):
    """Lo recién escrito (que aún está en el WAL) DEBE estar en la copia.
    Es justo lo que se pierde al copiar el .db a pelo."""
    db = _db_con_datos(tmp_path)
    esperado = sqlite3.connect(db.path).execute(
        "SELECT COUNT(*) FROM moderation_log").fetchone()[0]

    destino = backup_database(db.path)
    assert destino is not None and destino.exists()

    copia = sqlite3.connect(str(destino))
    assert copia.execute("SELECT COUNT(*) FROM moderation_log").fetchone()[0] == esperado
    assert copia.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_copia_es_consistente_mientras_se_escribe(tmp_path):
    """El bot no para de escribir de noche: la copia debe salir íntegra igual."""
    db = _db_con_datos(tmp_path)
    parar = threading.Event()

    def escritor():
        con = sqlite3.connect(db.path, timeout=30)
        while not parar.is_set():
            try:
                con.execute(
                    "INSERT INTO moderation_log (ts,chat_id,user_id,username,message_id,"
                    "rule,action,score,mode,payload_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (time.time(), -1, 1, "u", 1, "r", "noop", 0, "active", None))
                con.commit()
            except Exception:  # noqa: BLE001 — contención esperada, no es el objeto del test
                pass
        con.close()

    h = threading.Thread(target=escritor)
    h.start()
    time.sleep(0.1)
    try:
        destino = backup_database(db.path)
    finally:
        parar.set()
        h.join()

    assert destino is not None
    copia = sqlite3.connect(str(destino))
    assert copia.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_rotacion_conserva_las_mas_recientes(tmp_path):
    db = _db_con_datos(tmp_path)
    carpeta = Path(db.path).parent / "backups"
    carpeta.mkdir(parents=True, exist_ok=True)
    for i in range(1, 13):  # 12 copias viejas simuladas
        (carpeta / f"antispam-202601{i:02d}.db").write_bytes(b"x")

    backup_database(db.path)

    quedan = sorted(p.name for p in carpeta.glob("antispam-*.db"))
    assert len(quedan) == BACKUP_KEEP
    # la de hoy siempre sobrevive, y se van las más antiguas
    assert quedan[-1].startswith("antispam-")
    assert "antispam-20260101.db" not in quedan


def test_reejecutar_el_mismo_dia_rehace_la_copia(tmp_path):
    """VACUUM INTO falla si el destino existe: debe sobrescribir, no reventar."""
    db = _db_con_datos(tmp_path)
    primera = backup_database(db.path)
    assert primera is not None
    db.log_action(chat_id=-100, user_id=999, username="nuevo", message_id=1,
                  rule="test", action="noop", score=1, mode="active", payload=None)
    segunda = backup_database(db.path)
    assert segunda is not None and segunda == primera
    copia = sqlite3.connect(str(segunda))
    # la segunda copia refleja el dato añadido después de la primera
    assert copia.execute(
        "SELECT COUNT(*) FROM moderation_log WHERE username='nuevo'").fetchone()[0] == 1


def test_fallo_no_revienta_y_devuelve_none(tmp_path):
    """Sin copia se sigue: el mantenimiento nocturno nunca debe abortar por esto."""
    assert backup_database(tmp_path / "no" / "existe" / "x.db") is None


def test_keep_cero_no_borra_nada(tmp_path):
    """keep=0 desactiva la rotación en vez de dejar la carpeta vacía."""
    db = _db_con_datos(tmp_path)
    carpeta = Path(db.path).parent / "backups"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "antispam-20260101.db").write_bytes(b"x")
    backup_database(db.path, keep=0)
    assert (carpeta / "antispam-20260101.db").exists()
