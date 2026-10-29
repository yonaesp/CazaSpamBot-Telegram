"""La simulación realista (scripts/simular.py) forma parte de la suite.

Pasa conversaciones enteras por on_message con el reloj avanzando, en su propio
proceso (cambia time.time y bloquea la red, y eso no puede tocar al resto de
tests). La primera pasada destapó dos fallos que los tests unitarios no veían (L48).
"""
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_todas_las_escenas_dan_lo_esperado():
    r = subprocess.run([sys.executable, "scripts/simular.py", "--vacia"], cwd=_ROOT,
                       capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
