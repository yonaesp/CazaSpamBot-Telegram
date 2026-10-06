"""Escribir pronto no castiga a quien el bot ya da por legítimo.

Caso real (6-oct-2026, Windows 11): «Saizor», cuenta de 2.885 días con 20 fotos,
a quien al entrar se le saltó la verificación por tener perfil legítimo. Escribió
«BUENAS» a los 3 s y se le expulsó por `jfm_too_fast`; volvió a entrar, escribió
«HOLA» a los 3 s y otra expulsión.

Histórico de `jfm_too_fast` como regla única: 2 aciertos (PopcornTV con enlace a
astrurl.io, y 1xbet) y este falso positivo. La guarda solo perdona cuando NO hay
nada más que la prisa, así que el de PopcornTV sigue cayendo.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace as NS

from src import handlers, verification
from src.detectors import Hit

PRISA = [Hit(rule="jfm_too_fast", score=80, reason="r", payload={"delta_s": 3})]
SPAM_POPCORN = ("All movies & series available in PopcornTV ⭐🤩\n\n"
                "Netflix & Disney Plus and more\n\nJoin now: https://astrurl.io/p")


def _msg(text="BUENAS", **kw):
    base = dict(text=text, caption=None, entities=(), caption_entities=[],
                forward_origin=None, reply_markup=None)
    base.update(kw)
    return NS(**base)


def test_el_saludo_de_saizor_es_solo_prisa():
    assert handlers._solo_prisa_sin_contenido(_msg("BUENAS"), PRISA)
    assert handlers._solo_prisa_sin_contenido(_msg("HOLA"), PRISA)


def test_popcorntv_no_es_solo_prisa():
    """El acierto conocido lleva enlace: sigue castigándose."""
    assert not handlers._solo_prisa_sin_contenido(_msg(SPAM_POPCORN), PRISA)


def test_cualquier_contenido_rompe_la_guarda():
    casos = [
        _msg("mira t.me/canal"),
        _msg("escríbeme a @ofertas_top"),
        _msg("hola", entities=[NS(type="text_link")]),
        _msg("hola", forward_origin=NS(type="channel")),
        _msg("hola", reply_markup=NS()),
        _msg(None, photo=[NS()]),
        _msg(None, sticker=NS()),
    ]
    for m in casos:
        assert not handlers._solo_prisa_sin_contenido(m, PRISA), m


def test_otra_regla_junto_a_la_prisa_rompe_la_guarda():
    real = PRISA + [Hit(rule="commercial_ad", score=60, reason="r")]
    assert not handlers._solo_prisa_sin_contenido(_msg("hola"), real)


def test_tuple_mas_list_no_revienta():
    """entities como tupla (PTB) y caption_entities como lista (dobles)."""
    m = _msg("hola", entities=(NS(type="bold"),), caption_entities=[NS(type="italic")])
    assert handlers._solo_prisa_sin_contenido(m, PRISA)


def _sig(fotos, dias):
    return NS(photo_count=fotos, account_age_days=dias)


def test_el_perfil_de_saizor_es_legitimo_y_uno_nuevo_no():
    assert verification._is_very_legit_profile(_sig(20, 2885), "Lupe_maldonado", "Saizor")[0]
    assert not verification._is_very_legit_profile(_sig(0, 2885), None, "X")[0]
    assert not verification._is_very_legit_profile(_sig(3, 40), None, "X")[0]
    assert not verification._is_very_legit_profile(None, None, "X")[0]


def _on_message_src() -> str:
    fuente = Path("src/handlers.py").read_text()
    nodo = next(n for n in ast.walk(ast.parse(fuente))
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_message")
    return ast.get_source_segment(fuente, nodo)


def test_la_guarda_va_tras_decidir_y_exige_perfil_legitimo():
    src = _on_message_src()
    i_dec = src.index("decision = decide(")
    i_guarda = src.index("_solo_prisa_sin_contenido(msg, real)")
    assert i_dec < i_guarda
    tramo = src[i_guarda:i_guarda + 900]
    assert "_is_very_legit_profile(" in tramo, "sin perfil legítimo no se perdona"
    assert 'action="noop_prisa_legitimo"' in tramo, "debe quedar auditado"
