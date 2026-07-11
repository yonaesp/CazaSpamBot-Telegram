"""Tests de la traducción de reglas a explicación comprensible."""
from __future__ import annotations

from src.rule_explain import explain


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


def test_todas_las_reglas_de_spam_estan_mapeadas():
    """Meta-test: cualquier regla de baneo del código debe tener explicación.
    Si añades un detector nuevo y olvidas el motivo, este test falla."""
    import glob
    import re

    from src.rule_explain import RULE_EXPLANATIONS
    # Reglas que NO son baneos de spam (no salen en el aviso antispam):
    NO_ES_BAN = {"manual_admin_unban", "review_resolved"}
    rules = set()
    for f in glob.glob("src/**/*.py", recursive=True):
        with open(f, encoding="utf-8") as fh:
            # [^"{] excluye las dinámicas (f-string con {id})
            for m in re.findall(r'rule=f?"([^"{]+)"', fh.read()):
                if m and m != "+":
                    rules.add(m)
    faltan = sorted(r for r in rules if r not in RULE_EXPLANATIONS and r not in NO_ES_BAN)
    assert not faltan, f"Reglas sin explicación en rule_explain.py: {faltan}"
