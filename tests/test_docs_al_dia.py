"""Los números que dicen los docs tienen que ser los de verdad.

`README.md`, `docs/ARCHITECTURE.md` y `docs/ROADMAP.md` presumen de «N tests» y «N
detectores». Esos números se actualizaban a mano, en cuatro ficheros, cada vez que
se añadía algo, y era cuestión de tiempo que se quedaran viejos: el README llegó a
decir 1018 tests cuando ya iban por 1146. Un dato desactualizado en el README es
peor que no ponerlo, porque quien lo lee no tiene forma de saber que miente.

Este test los compara con la realidad y falla si alguien añade un detector o unos
tests y no toca la documentación. Es el item 1 del roadmap y lo que lo justificaba
era justo esto: lo que no se comprueba, se pudre.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

# Por debajo de esto se asume que se está ejecutando UN fichero suelto, no la
# suite: el número de tests recogidos no sería comparable y el test se salta.
# Sin esta guarda, `pytest tests/test_locales.py` fallaría aquí sin motivo.
_MINIMO_SUITE = 500


def _detectores_reales() -> int:
    return len([f for f in (RAIZ / "src" / "detectors").glob("*.py")
                if f.stem != "__init__"])


def _numeros(patron: str, *ficheros: str) -> list[tuple[str, int]]:
    """(fichero, número) de cada sitio donde el patrón case."""
    fuera = []
    for nombre in ficheros:
        texto = (RAIZ / nombre).read_text(encoding="utf-8")
        for m in re.finditer(patron, texto):
            fuera.append((nombre, int(m.group(1).replace(".", ""))))
    return fuera


def test_los_docs_dicen_los_detectores_que_hay():
    reales = _detectores_reales()
    citados = _numeros(r"(\d+)\s+detectores?\b", "docs/ARCHITECTURE.md", "docs/ROADMAP.md")
    citados += _numeros(r"(\d+)\s+detectors?\b", "README.md")
    assert citados, "ningún doc dice cuántos detectores hay"
    malos = [(f, n) for f, n in citados if n != reales]
    assert not malos, (
        f"hay {reales} detectores en src/detectors/ y los docs dicen otra cosa: {malos}. "
        "Actualiza el número donde toque.")


def test_los_docs_dicen_los_tests_que_hay(request):
    """El número real lo da la propia sesión de pytest, que es la única fuente
    fiable: contar `def test_` a mano se equivoca con `parametrize`."""
    reales = getattr(request.session, "testscollected", 0)
    if reales < _MINIMO_SUITE:
        pytest.skip("se está ejecutando un subconjunto, no la suite entera")
    citados = _numeros(r"(\d[\d.]*)\s+tests\b", "README.md", "docs/ARCHITECTURE.md",
                       "docs/ROADMAP.md")
    citados += _numeros(r"tests-(\d+)%20passing", "README.md")
    assert citados, "ningún doc dice cuántos tests hay"
    malos = [(f, n) for f, n in citados if n != reales]
    assert not malos, (
        f"la suite tiene {reales} tests y los docs dicen otra cosa: {malos}. "
        "Actualiza el número donde toque (README badge incluido).")


def test_cada_detector_sabe_explicarse():
    """Un detector cuya regla no esté en `rule_explain` deja al admin leyendo un
    identificador técnico en el aviso, que es el texto más visible del bot."""
    from src.rule_explain import KNOWN_RULES
    from src.locales import STRINGS
    faltan = [r for r in KNOWN_RULES if f"rule.{r}" not in (STRINGS.get("es") or {})]
    assert not faltan, f"reglas sin explicación en es.json: {faltan}"
