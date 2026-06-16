"""Tests del detector join-to-first-message (jfm_delta)."""
from __future__ import annotations

from src.detectors import jfm_delta as det

MUTE_SCORE = 40  # umbral por defecto de mute


def test_no_primer_mensaje_no_dispara():
    assert det.check(is_first_msg=False, delta_seconds=2).score == 0


def test_sin_delta_no_dispara():
    assert det.check(is_first_msg=True, delta_seconds=None).score == 0


def test_instantaneo_es_bot_probable():
    """< 5s sigue siendo señal fuerte que actúa sola."""
    hit = det.check(is_first_msg=True, delta_seconds=2)
    assert hit.rule == "jfm_too_fast"
    assert hit.score == 80


def test_rapido_no_mutea_solo():
    """< 30s es señal DÉBIL: por debajo del umbral de mute, no actúa sola.

    Un humano que verifica y responde rápido es legítimo; solo cuenta si se
    combina con otra señal (esto evita el falso positivo del usuario eager).
    """
    hit = det.check(is_first_msg=True, delta_seconds=11)
    assert hit.rule == "jfm_fast"
    assert hit.score == 30
    assert hit.score < MUTE_SCORE


def test_normal_no_dispara():
    """Tiempos humanos normales (minutos) no disparan nada."""
    assert det.check(is_first_msg=True, delta_seconds=600).score == 0
