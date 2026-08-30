"""Tests para _is_very_legit_profile."""
from __future__ import annotations

from types import SimpleNamespace

from src.verification import _is_very_legit_profile


def _sig(photo_count=2, account_age_days=500):
    return SimpleNamespace(photo_count=photo_count, account_age_days=account_age_days)


def test_no_sig_not_legit():
    legit, _ = _is_very_legit_profile(None, "user", "Juan", "Pérez")
    assert legit is False


def test_una_foto_antigua_ya_es_legit():
    """Antes se exigían DOS fotos y este test fijaba lo contrario. Lo cambió un
    caso real (30-ago-2026): «mario», nombre latino, 1 foto de hace 540 días y sin
    username, acabó con «verifica en 30 min o serás expulsado». Medido después
    sobre 20 usuarios asentados del grupo, el 15 % tiene una sola foto.

    Lo que la condición quiere probar es la ANTIGÜEDAD, y esa se calcula con la
    foto más vieja: una de hace año y medio la demuestra igual que dos."""
    legit, _ = _is_very_legit_profile(_sig(photo_count=1), "user", "Juan", "Pérez")
    assert legit is True


def test_sin_ninguna_foto_sigue_sin_ser_legit():
    legit, _ = _is_very_legit_profile(_sig(photo_count=0), "user", "Juan", "Pérez")
    assert legit is False


def test_young_account_not_legit():
    legit, _ = _is_very_legit_profile(_sig(account_age_days=100), "user", "Juan", "Pérez")
    assert legit is False


def test_no_age_info_not_legit():
    legit, _ = _is_very_legit_profile(_sig(account_age_days=None), "user", "Juan", "Pérez")
    assert legit is False


def test_non_latin_name_not_legit():
    legit, _ = _is_very_legit_profile(_sig(), "user", "李雷", "Pérez")
    assert legit is False


def test_non_latin_username_not_legit():
    legit, _ = _is_very_legit_profile(_sig(), "用户", "Juan", "Pérez")
    assert legit is False


def test_all_conditions_met_is_legit():
    legit, reasons = _is_very_legit_profile(_sig(photo_count=5, account_age_days=730), "juan_user", "Juan", "Pérez")
    assert legit is True
    assert any("5 fotos" in r for r in reasons)
    assert any("730d" in r for r in reasons)
    assert any("latino" in r for r in reasons)


def test_exactly_boundary_2_fotos_365_dias():
    legit, _ = _is_very_legit_profile(_sig(photo_count=2, account_age_days=365), "u", "Ana", None)
    assert legit is True


def test_no_username_but_name_latino_legit():
    """Sin username pero todo lo demás OK: legit."""
    legit, _ = _is_very_legit_profile(_sig(), None, "Maria", "Garcia")
    assert legit is True
