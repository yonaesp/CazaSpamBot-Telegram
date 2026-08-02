"""Meta-tests de la capa de ajustes: cosas que se desincronizan solas.

Cada uno de estos cubre un fallo REAL que ya ocurrió, en vez de acordarse de
escribir un test por campo cada vez que se añade una columna.
"""
import re
from pathlib import Path

from src.db import DB


def _columnas_chat_settings(tmp_path) -> set[str]:
    db = DB(str(tmp_path / "t.db"))
    with db._cur() as c:
        filas = c.execute("PRAGMA table_info(chat_settings)").fetchall()
    return {f[1] for f in filas}


def test_toda_columna_por_chat_se_puede_escribir(tmp_path):
    """Una columna fuera de la lista ALLOWED existe pero NO se puede escribir:
    el panel la ofrecería y el ajuste no se guardaría, en silencio."""
    fuente = Path("src/db.py").read_text()
    i = fuente.index("        ALLOWED = {")
    bloque = fuente[i:fuente.index("}", i)]
    permitidas = set(re.findall(r'"([a-z_]+)"', bloque))
    columnas = _columnas_chat_settings(tmp_path) - {"chat_id", "updated_at"}
    faltan = columnas - permitidas
    # verification_suspicious_kick_h está marcada como sin uso en el esquema.
    faltan.discard("verification_suspicious_kick_h")
    assert not faltan, f"columnas que no se pueden escribir: {sorted(faltan)}"


def test_el_esquema_y_la_migracion_dan_el_mismo_defecto(tmp_path):
    """Fallo real: el esquema decía DEFAULT 1 y la migración DEFAULT 0 para
    `verification_review_suspicious`. Resultado: las instalaciones NUEVAS tenían la
    revisión de sospechosos encendida y las que ACTUALIZARON, apagada, sin que
    nadie se enterara. Los tres grupos de producción se quedaron a 0.
    """
    fuente = Path("src/db.py").read_text()
    esquema = dict(re.findall(r"^\s{4}([a-z_]+) INTEGER NOT NULL DEFAULT (\d+)", fuente, re.M))
    migracion = dict(re.findall(
        r"ADD COLUMN ([a-z_]+) INTEGER NOT NULL DEFAULT (\d+)", fuente))
    discrepan = {c: (esquema[c], migracion[c]) for c in migracion
                 if c in esquema and esquema[c] != migracion[c]}
    assert not discrepan, (
        f"el esquema y la migración discrepan: {discrepan}. Una instalación nueva y "
        f"una actualizada acabarían con ajustes distintos y sin avisar."
    )


def test_los_comandos_de_ajustes_respetan_el_sync():
    """Fallo real: el panel propagaba a todos los grupos con /sync ON y el comando
    equivalente escribía solo en uno, así que el MISMO ajuste acababa en sitios
    distintos según por dónde lo tocaras."""
    sospechosos = []
    for ruta in ("src/warns_mod.py", "src/admin.py", "src/config_panel.py"):
        for n, linea in enumerate(Path(ruta).read_text().splitlines(), 1):
            if "db.update_chat_setting(" in linea and "def " not in linea:
                sospechosos.append(f"{ruta}:{n}")
    assert not sospechosos, (
        "escrituras directas que se saltan settings_sync (usa apply_setting): "
        + ", ".join(sospechosos)
    )


def test_el_modo_shadow_sobrevive_a_un_reinicio(tmp_path):
    """Fallo real: /shadow solo cambiaba el objeto en memoria. Un reinicio devolvía
    el bot al modo del .env sin decir nada, así que quien pasaba a activo y
    reiniciaba se quedaba sin moderación creyendo que la tenía."""
    db = DB(str(tmp_path / "t.db"))
    assert db.get_pref("mode_shadow") is None, "por defecto manda el .env"
    db.set_pref("mode_shadow", False)
    assert db.get_pref("mode_shadow") is False

    arranque = Path("src/main.py").read_text()
    assert 'get_pref("mode_shadow")' in arranque, (
        "el arranque no consulta el modo persistido: /shadow se perderá al reiniciar")
    cmd = Path("src/admin.py").read_text()
    assert 'set_pref("mode_shadow"' in cmd, "/shadow no persiste la elección"
