"""Tests anti-FP del detector obvious_spam_profile.

Casos reales del incidente 2026-05-29 con 100+ FP por nombres decorativos
o usuarios bilingües legítimos.
"""
from __future__ import annotations

from types import SimpleNamespace

from src.verification import _is_obvious_spam_profile, _is_decorative_mix, _han_dominant


def test_han_dominant_chino_real():
    """Nombre dominado por ideogramas chinos (Han) → True (señal de spam)."""
    assert _han_dominant("苹果-web3前端") is True   # lurker baneado 2026-06-22
    assert _han_dominant("看直播赚钱") is True       # spam chino típico


def test_han_dominant_no_decorativo_ni_legitimo():
    """Katakana decorativo, latino o 1 Han suelto → False (no es chino dominante)."""
    assert _han_dominant("Lore ツ") is False         # katakana, no Han
    assert _han_dominant("フアン・ホセ") is False      # katakana
    assert _han_dominant("Óscar") is False
    assert _han_dominant("Pro苹") is False            # 1 solo Han
    assert _han_dominant("") is False
    assert _han_dominant(None) is False


def test_obvious_spam_han_un_solo_campo():
    """1 campo en chino real (aunque username sea latino) → ban directo."""
    ok, _ = _is_obvious_spam_profile(None, "liousweb3", "苹果-web3前端", None)
    assert ok is True


def test_obvious_spam_katakana_decorativo_no():
    """Katakana decorativo NO debe disparar (sería FP como el incidente de mayo)."""
    ok, _ = _is_obvious_spam_profile(None, None, "Lore", "ツ")
    assert ok is False


def _sig(photo_count=2, account_age_days=500):
    return SimpleNamespace(photo_count=photo_count, account_age_days=account_age_days)


# ─────────── tests anti-FP (NO deben disparar) ───────────

def test_marcospg24_thai_cyrillic_decorative():
    """๓คгς๏รקg24 (Thai+Cyrillic+Greek+Hebrew emulando 'marcospg24'). NO ban."""
    legit, _ = _is_obvious_spam_profile(None, "MARCOSPG24", "๓คгς๏รקg24", None)
    assert legit is False


def test_vapersextrem_cherokee_decorative():
    """ᏙᎪᏢᎬᎡՏᎬХͲᎡᎬᎷ (Cherokee+Cyrillic+Greek emulando 'VAPERSEXTREM'). NO ban."""
    legit, _ = _is_obvious_spam_profile(None, "vapersextrem", "🇪🇸 ᏙᎪᏢᎬᎡՏᎬХͲᎡᎬᎷ 🇪🇸", None)
    assert legit is False


def test_mathematical_alphanumeric_normaliza_a_latin():
    """𝓜𝓪𝓻𝓲𝓪 (Mathematical Script Bold). NFKC lo normaliza a Maria. NO ban."""
    legit, _ = _is_obvious_spam_profile(None, "maria_lopez", "𝓜𝓪𝓻𝓲𝓪", None)
    assert legit is False


def test_fullwidth_latin_normaliza():
    """Ｍａｒｉａ (Fullwidth Latin). NFKC normaliza a Maria. NO ban."""
    legit, _ = _is_obvious_spam_profile(None, "maria", "Ｍａｒｉａ", None)
    assert legit is False


def test_persa_bilingue_con_username_latino_no_ban():
    """مهدی + username @mahdi_beygjani + Telethon dice cuenta con foto y antigua."""
    sig = _sig(photo_count=2, account_age_days=1000)
    legit, _ = _is_obvious_spam_profile(sig, "mahdi_beygjani", "مهدی", None)
    assert legit is False


def test_arabic_solo_con_foto_y_antiguo_no_ban():
    """1 campo árabe puro pero con foto y cuenta antigua = legítimo."""
    sig = _sig(photo_count=3, account_age_days=500)
    legit, _ = _is_obvious_spam_profile(sig, None, "أحمد", None)
    assert legit is False


def test_cyrillic_solo_con_foto_y_antiguo_no_ban():
    """1 campo cirílico puro pero perfil completo = legítimo."""
    sig = _sig(photo_count=2, account_age_days=900)
    legit, _ = _is_obvious_spam_profile(sig, "ivan_petrov", "Иван", "Петров")
    assert legit is False


def test_sin_telethon_y_un_solo_campo_no_latin_no_ban():
    """Sin info Telethon: 1 campo no-latín solo NO basta. Era el bug."""
    legit, _ = _is_obvious_spam_profile(None, "carlos_es", "مهدي", None)
    assert legit is False


# ─────────── tests SI deben disparar (spam real) ───────────

def test_arabic_puro_sin_foto_cuenta_nueva_si_ban():
    """First_name árabe puro + cuenta sin foto + nueva = SPAM REAL."""
    sig = _sig(photo_count=0, account_age_days=5)
    legit, reasons = _is_obvious_spam_profile(sig, None, "أحمد سبام", None)
    assert legit is True
    assert any("sin foto" in r for r in reasons)


def test_2_campos_non_latin_si_ban():
    """2+ campos non-latin = ban directo (sin necesidad de Telethon)."""
    legit, _ = _is_obvious_spam_profile(None, "иван_спам", "Иван", "Спамеров")
    assert legit is True


def test_hebrew_puro_sin_telethon_no_ban():
    """Sin sig, 1 campo hebreo NO ban (puede ser usuario real). Cambia de antes."""
    legit, _ = _is_obvious_spam_profile(None, None, "אבי", None)
    assert legit is False


# ─────────── tests de _is_decorative_mix directamente ───────────

def test_decorative_mix_3_scripts():
    assert _is_decorative_mix("๓คгς๏รקg24") is True  # Thai+Cyrillic+Hebrew+Greek+Latin


def test_decorative_mix_cherokee_cyrillic_greek():
    assert _is_decorative_mix("ᏙᎪᏢᎬᎡՏᎬХͲᎡᎬᎷ") is True


def test_decorative_mix_pure_arabic_no():
    """Árabe puro NO es decorativo, es un nombre real."""
    assert _is_decorative_mix("أحمد") is False


def test_decorative_mix_pure_cyrillic_no():
    assert _is_decorative_mix("Иван") is False


def test_decorative_mix_latin_only_no():
    assert _is_decorative_mix("Maria Garcia") is False


def test_decorative_mix_persian_only_no():
    assert _is_decorative_mix("مهدی") is False
