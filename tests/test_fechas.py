"""Toda hora que ve una persona sale en la misma zona horaria.

El bot mezcla dos orígenes y cada uno viene en una zona distinta:

- **base de datos y logs**: `time.time()` → se formatea en la zona del proceso
  (`Europe/Madrid` en este despliegue);
- **Telethon** (admin_log, fotos de perfil): datetimes **en UTC**, con `tzinfo`.

Formatearlos a pelo mezcla las dos cosas en la misma pantalla. `/quienfue`
mostraba las horas del registro de administración **dos horas atrasadas**
respecto a `/recent`, y nadie lo había notado porque las dos parecen plausibles.

Costó tiempo de verdad el 2026-08-23 investigando la queja de un usuario: los
logs decían 11:16 y el registro de Telegram 09:16, y parecían eventos distintos
cuando eran el mismo.
"""
import datetime as _dt
import time
from pathlib import Path

import pytest

from src import fechas


def test_un_datetime_en_utc_se_convierte():
    """El caso que estaba mal: Telethon da UTC y se mostraba sin convertir."""
    utc = _dt.datetime(2026, 8, 23, 9, 16, tzinfo=_dt.timezone.utc)
    esperado = utc.astimezone().strftime("%d/%m %H:%M")
    assert fechas.cuando(utc) == esperado


def test_un_epoch_de_la_base_se_muestra_igual_que_antes():
    ts = time.time()
    assert fechas.cuando(ts) == _dt.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


def test_los_dos_origenes_coinciden_en_el_mismo_instante():
    """La comprobación que importa: el MISMO momento, contado por la base y por
    Telethon, tiene que mostrarse con la misma hora."""
    ahora = time.time()
    desde_bd = fechas.cuando(ahora)
    desde_telethon = fechas.cuando(
        _dt.datetime.fromtimestamp(ahora, _dt.timezone.utc))
    assert desde_bd == desde_telethon


def test_un_datetime_sin_zona_se_toma_como_local():
    d = _dt.datetime(2026, 8, 23, 11, 16)
    assert fechas.cuando(d) == "23/08 11:16"


def test_una_fecha_suelta_no_inventa_horas():
    """La creación estimada de una cuenta es un día, sin hora ni zona."""
    assert fechas.dia(_dt.date(2022, 7, 14)) == "14/07/2022"


@pytest.mark.parametrize("basura", [None, "", "ayer", float("nan"), 10**20, object()])
def test_lo_ilegible_no_revienta(basura):
    """Esto se usa dentro de avisos: una fecha rara no puede tumbar el mensaje."""
    assert fechas.cuando(basura) == "?"


def test_se_puede_pedir_otro_formato():
    d = _dt.datetime(2026, 8, 23, 11, 16)
    assert fechas.cuando(d, "%Y-%m-%d %H:%M") == "2026-08-23 11:16"


# --------------------------------------------------- que no se vuelva a mezclar

def test_ningun_texto_para_personas_formatea_la_fecha_a_mano():
    """Meta-test. Las excepciones están justificadas en el propio código:
    `maintenance` usa UTC para un NOMBRE DE FICHERO y `topweekly` ya fija
    Madrid explícitamente."""
    permitidos = {"src/fechas.py", "src/maintenance.py", "src/topweekly.py"}
    malos = []
    for f in sorted(Path("src").rglob("*.py")):
        if str(f) in permitidos:
            continue
        for n, linea in enumerate(f.read_text().splitlines(), 1):
            if ".strftime(" in linea and not linea.strip().startswith("#"):
                malos.append(f"{f}:{n}: {linea.strip()}")
    assert not malos, (
        "fecha formateada a mano (usa `fechas.cuando()` / `fechas.dia()`):\n"
        + "\n".join(malos))


def test_las_excepciones_siguen_estando_justificadas():
    """Si alguien quita el porqué, el meta-test de arriba deja de tener sentido."""
    m = Path("src/maintenance.py").read_text()
    i = m.index('strftime("%Y%m%d")')
    assert "NOMBRE DE FICHERO" in m[max(0, i - 400):i]
    t = Path("src/topweekly.py").read_text()
    assert "TZ_MADRID" in t
