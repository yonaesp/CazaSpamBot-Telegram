"""Salud de los archivos de idioma (`src/locales/*.json`).

Estos tests existen porque los idiomas los puede aportar CUALQUIERA: deben poder
traducir sin romper el bot, y nosotros debemos enterarnos si algo no cuadra.

Tres niveles a propósito:
  1. DURO para todos los idiomas: JSON válido, texto plano, placeholders idénticos a
     los del español y HTML balanceado. Un fallo aquí sí rompe la experiencia.
  2. DURO solo para es↔en: paridad total de claves (son los idiomas oficiales).
  3. INFORMATIVO para idiomas de la comunidad: que estén incompletos es normal y NO
     debe romper el CI; lo que falte cae al español automáticamente.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from string import Formatter

import pytest

_DIR = Path(__file__).resolve().parents[1] / "src" / "locales"
_FALLBACK = "es"
_ARCHIVOS = sorted(_DIR.glob("*.json"))
_CODIGOS = [p.stem for p in _ARCHIVOS]


def _cargar(code: str) -> dict:
    return json.loads((_DIR / f"{code}.json").read_text(encoding="utf-8"))


def _placeholders(texto: str) -> set[str]:
    return {f for _, f, _, _ in Formatter().parse(texto) if f}


def test_hay_idiomas_y_esta_el_de_referencia():
    assert _CODIGOS, "no se encontró ningún archivo de idioma"
    assert _FALLBACK in _CODIGOS, "falta el idioma de referencia es.json"


@pytest.mark.parametrize("code", _CODIGOS)
def test_json_valido_y_solo_texto(code):
    """Debe ser un objeto {clave: texto}. Nada de listas, números ni anidamiento."""
    data = _cargar(code)
    assert isinstance(data, dict), f"{code}.json debe ser un objeto JSON"
    malos = [k for k, v in data.items() if not isinstance(v, str)]
    assert not malos, f"{code}.json: valores que no son texto: {malos[:5]}"


@pytest.mark.parametrize("code", [c for c in _CODIGOS if c != _FALLBACK])
def test_placeholders_identicos_al_espanol(code):
    """Si una traducción escribe {nombre} donde el original dice {n}, el texto sale
    roto (t() no puede sustituirlo). Se comprueba clave a clave."""
    base, otro = _cargar(_FALLBACK), _cargar(code)
    fallos = []
    for clave, texto_es in base.items():
        if clave not in otro:
            continue  # incompleto es aceptable: cae al español
        esperados, recibidos = _placeholders(texto_es), _placeholders(otro[clave])
        if esperados != recibidos:
            fallos.append(f"{clave}: es={sorted(esperados)} vs {code}={sorted(recibidos)}")
    assert not fallos, f"placeholders que no cuadran en {code}.json:\n  " + "\n  ".join(fallos)


@pytest.mark.parametrize("code", _CODIGOS)
def test_html_balanceado(code):
    """Telegram rechaza el mensaje ENTERO si el HTML está mal cerrado (BadRequest:
    can't parse entities). En un bot de moderación eso puede ser un aviso de ban que
    se pierde en silencio, así que se comprueba etiqueta por etiqueta."""
    data = _cargar(code)
    fallos = []
    for clave, texto in data.items():
        for tag in ("b", "i", "u", "s", "code", "pre", "a"):
            abre = len(re.findall(rf"<{tag}(?:\s[^>]*)?>", texto))
            cierra = len(re.findall(rf"</{tag}>", texto))
            if abre != cierra:
                fallos.append(f"{clave}: <{tag}> x{abre} vs </{tag}> x{cierra}")
    assert not fallos, f"HTML desbalanceado en {code}.json:\n  " + "\n  ".join(fallos)


def test_paridad_total_es_en():
    """es y en son los idiomas oficiales: deben tener EXACTAMENTE las mismas claves.
    (A los idiomas de la comunidad no se les exige esto.)"""
    es, en = _cargar("es"), _cargar("en")
    faltan = sorted(set(es) - set(en))
    sobran = sorted(set(en) - set(es))
    assert not faltan, f"claves sin traducir en en.json: {faltan}"
    assert not sobran, f"claves de más en en.json (¿sobran o faltan en es?): {sobran}"


def test_cobertura_idiomas_comunidad_informativa(capsys):
    """NO falla por estar incompleto: solo informa. Un idioma al 60% es útil."""
    base = _cargar(_FALLBACK)
    for code in _CODIGOS:
        if code in (_FALLBACK, "en"):
            continue
        cubiertas = len(set(_cargar(code)) & set(base))
        with capsys.disabled():
            print(f"  [i18n] {code}.json: {cubiertas}/{len(base)} claves "
                  f"({cubiertas * 100 // max(len(base), 1)}%)")
