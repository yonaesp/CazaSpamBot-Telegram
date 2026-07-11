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
