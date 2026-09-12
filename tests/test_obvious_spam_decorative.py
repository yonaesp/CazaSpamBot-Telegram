"""Tests anti-FP del detector obvious_spam_profile.

Casos reales del incidente 2026-05-29 con 100+ FP por nombres decorativos
o usuarios bilingües legítimos.
"""
from __future__ import annotations

from types import SimpleNamespace

from src import verification as v
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




# ══════════════════════════════════════════════════════════════════════════════
# CAMBIO DE POLÍTICA (13-sep-2026, decisión explícita del admin)
#
# Un SOLO campo con el nombre entero (>=70%, y al menos 3 letras) en un alfabeto
# que el chat no permite es ban directo, **sin excepciones**: el criterio se
# evalúa ANTES del salvoconducto de «cuenta antigua con foto», así que una cuenta
# de cinco años con foto y nombre en árabe o cirílico se banea igual.
#
# Se le presentó el coste al admin —cualquier persona real con nombre en árabe,
# ruso, griego o hebreo queda fuera de sus grupos para siempre— y lo aceptó.
#
# El dato con el que se decidió: sobre las 566 personas con nombre registrado, el
# criterio cambia el veredicto de 9, TODAS con 0 mensajes, y 5 ya estaban baneadas
# por otra vía. El único veterano con nombre exótico (220 mensajes desde 2022) no
# se ve afectado: tras NFKC queda en 22% no latino.
#
# Los tests de abajo fijaban la política ANTERIOR y se han invertido a propósito.
# Lo que NO ha cambiado, y sigue con sus tests intactos más arriba, es el anti-FP
# de los adornos: `ツ`, `彡` o `♛` sueltos no son un nombre (de ahí el mínimo de 3
# letras) y las mezclas decorativas de 3+ alfabetos se siguen ignorando.
# ══════════════════════════════════════════════════════════════════════════════

def test_persa_bilingue_con_username_latino_AHORA_SI_BAN():
    """مهدی + @mahdi_beygjani + cuenta de 1000 días con foto.

    Este es el coste que el admin aceptó con los ojos abiertos: una persona real,
    bilingüe y con la cuenta asentada, cae igual. Antes se libraba por tener el
    usuario en latín y el salvoconducto de antigüedad.
    """
    sig = _sig(photo_count=2, account_age_days=1000)
    legit, _ = _is_obvious_spam_profile(sig, "mahdi_beygjani", "مهدی", None)
    assert legit is True


def test_arabic_solo_con_foto_y_antiguo_AHORA_SI_BAN():
    """El salvoconducto de «cuenta antigua con foto» ya no cubre esto."""
    sig = _sig(photo_count=3, account_age_days=500)
    legit, _ = _is_obvious_spam_profile(sig, None, "أحمد", None)
    assert legit is True


def test_cyrillic_solo_con_foto_y_antiguo_AHORA_SI_BAN():
    """Iván Petrov con 900 días y foto: cae igual. Es la política que se pidió.

    Ojo, este perfil ya caía antes por tener DOS campos en cirílico; lo que cambia
    es que ahora ni siquiera llega al salvoconducto.
    """
    sig = _sig(photo_count=2, account_age_days=900)
    legit, _ = _is_obvious_spam_profile(sig, "ivan_petrov", "Иван", "Петров")
    assert legit is True


def test_sin_telethon_y_un_solo_campo_no_latin_AHORA_SI_BAN():
    """Ya no hace falta Telethon: el nombre solo basta, lo diga quien lo diga."""
    legit, _ = _is_obvious_spam_profile(None, "carlos_es", "مهدي", None)
    assert legit is True


# ─────────── tests SI deben disparar (spam real) ───────────

def test_arabic_puro_sin_foto_cuenta_nueva_si_ban():
    """First_name árabe puro + cuenta sin foto + nueva = SPAM REAL."""
    sig = _sig(photo_count=0, account_age_days=5)
    legit, reasons = _is_obvious_spam_profile(sig, None, "أحمد سبام", None)
    assert legit is True
    # motivos = CÓDIGOS estables (no texto): así el payload en BD no depende del idioma
    # El motivo ahora es el criterio nuevo, que se evalúa antes que el de
    # «sin foto + cuenta nueva». Sigue siendo ban, y sigue siendo un CÓDIGO
    # estable (no texto), que es lo que este test protege.
    assert v.REASON_SINGLE_FIELD_SCRIPT in [code for code, _ in reasons]


def test_2_campos_non_latin_si_ban():
    """2+ campos non-latin = ban directo (sin necesidad de Telethon)."""
    legit, _ = _is_obvious_spam_profile(None, "иван_спам", "Иван", "Спамеров")
    assert legit is True


def test_hebrew_puro_sin_telethon_AHORA_SI_BAN():
    """«אבי» son 3 letras justas, así que pasa el mínimo y cae."""
    legit, _ = _is_obvious_spam_profile(None, None, "אבי", None)
    assert legit is True


def test_los_adornos_de_una_o_dos_letras_siguen_a_salvo():
    """El mínimo de 3 letras es lo que impide que la política nueva reviva el
    falso positivo de mayo: `ツ`, `彡` o `♛` no son un nombre, son un adorno."""
    for nombre, apellido in (("Lore", "ツ"), ("Jonatan", "彡"), ("Ana", "♛"),
                             ("Carlos", "ッ"), ("María", "☆")):
        ok, _ = _is_obvious_spam_profile(None, None, nombre, apellido)
        assert ok is False, f"{nombre} {apellido} no debería caer"


def test_el_criterio_respeta_los_alfabetos_DEL_CHAT():
    """Un grupo que permita cirílico no se autodestruye al actualizar."""
    ok, _ = _is_obvious_spam_profile(None, None, "Фёдор", None,
                                     allowed_scripts=["latin", "cyrillic"])
    assert ok is False
    ok, _ = _is_obvious_spam_profile(None, None, "Фёдор", None,
                                     allowed_scripts=["latin"])
    assert ok is True


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
