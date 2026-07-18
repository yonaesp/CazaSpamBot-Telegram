"""Tests de la traducción de reglas a explicación comprensible."""
from __future__ import annotations

import pytest

from src import i18n
from src.rule_explain import explain


@pytest.fixture(autouse=True)
def _es():
    """Los textos viven en los paquetes de idioma: se fija ES para no depender del
    idioma global que haya dejado otro test."""
    previo = i18n.current_lang()
    i18n.set_lang("es")
    yield
    i18n.set_lang(previo)


def test_reglas_de_los_ejemplos_del_user():
    assert "botones" in explain("inline_buttons_from_user").lower()
    e = explain("non_allowed_script").lower()
    assert "alfabeto no permitido" in e or "chino" in e


def test_regla_combinada_une_explicaciones():
    e = explain("jfm_fast+non_allowed_script")
    assert "·" in e  # dos motivos unidos


def test_combinada_repetida_no_duplica():
    assert explain("cas_match+cas_match") == explain("cas_match")


def test_desconocida_o_vacia_devuelve_vacio():
    assert explain("regla_que_no_existe_xyz") == ""
    assert explain("") == ""


def test_clave_ausente_del_paquete_devuelve_vacio(monkeypatch):
    """Guarda anti-«rule.xxx» en pantalla: si la clave falta en los paquetes de idioma,
    `t()` devuelve la propia clave (truthy) y el admin vería el identificador crudo en
    vez del motivo de respaldo. explain() debe devolver algo FALSY."""
    from src import locales

    sin_clave = {k: v for k, v in locales.STRINGS["es"].items() if k != "rule.cas_match"}
    monkeypatch.setitem(locales.STRINGS, "es", sin_clave)
    assert explain("cas_match") == ""


def test_todas_las_reglas_conocidas_tienen_texto_en_todos_los_idiomas():
    """Cada regla del inventario debe tener su `rule.<id>` en TODOS los paquetes."""
    from src import locales
    from src.rule_explain import KNOWN_RULES

    for lang, strings in locales.STRINGS.items():
        faltan = sorted(r for r in KNOWN_RULES if f"rule.{r}" not in strings)
        assert not faltan, f"Sin traducir en {lang}.json: {faltan}"


def test_todas_las_reglas_de_spam_estan_mapeadas():
    """Meta-test: cualquier regla de baneo del código debe tener explicación.
    Si añades un detector nuevo y olvidas el motivo, este test falla."""
    import glob
    import re

    from src.rule_explain import KNOWN_RULES
    # Reglas que NO son baneos de spam (no salen en el aviso antispam):
    NO_ES_BAN = {"manual_admin_unban", "review_resolved"}
    rules = set()
    for f in glob.glob("src/**/*.py", recursive=True):
        with open(f, encoding="utf-8") as fh:
            # [^"{] excluye las dinámicas (f-string con {id})
            for m in re.findall(r'rule=f?"([^"{]+)"', fh.read()):
                if m and m != "+":
                    rules.add(m)
    faltan = sorted(r for r in rules if r not in KNOWN_RULES and r not in NO_ES_BAN)
    assert not faltan, f"Reglas sin explicación en rule_explain.py: {faltan}"
