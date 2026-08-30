"""No tener @usuario no es motivo para el plazo corto, ni una sola foto para el gate.

Caso medido (30-ago-2026, Windows 11): «mario», nombre latino, **una foto de hace
540 días**, sin @usuario. El bot le pidió verificación con el tier duro:
«Cuenta sospechosa (sin username): verifica en 30 min o serás expulsado».

Los dos motivos, y lo que dicen los datos del propio grupo:

- **`no_username` bastaba para el tier de 30 minutos.** Medido sobre los miembros
  reales: **29 %** en Windows 11 (454 de 1554) y **14 %** en Domótica (479 de
  3414) no tienen username. La lista `_STRONG_SUSP_REASONS` ya existía y ya
  excluía esta señal, pero solo se usaba para decidir si avisar al admin.
- **`_is_very_legit_profile` exigía 2 fotos.** Sobre una muestra de 20 usuarios
  asentados (≥10 mensajes), **el 15 % tiene una sola**. Y lo que esa condición
  quiere probar es la ANTIGÜEDAD, que se calcula con la foto más vieja: una foto
  de hace año y medio la demuestra igual que dos.

Nada de esto relaja la detección: los detectores de perfil y de mensaje siguen
aplicándose enteros. Lo único que cambia es a quién se le pone el botón delante.
"""
from types import SimpleNamespace as NS

import pytest

from src import verification as v


def _sig(fotos=1, dias=540, bio=None):
    return NS(photo_count=fotos, account_age_days=dias, bio=bio, is_premium=False,
              oldest_photo=None, personal_channel_title=None, personal_channel_id=None)


# ------------------------------------------------------------ el caso de mario

def test_mario_se_libra_del_gate():
    ok, razones = v._is_very_legit_profile(_sig(), None, "mario", None)
    assert ok, f"sigue pasando por verificación: {razones}"


def test_una_sola_foto_antigua_basta():
    """La antigüedad se calcula con la foto más vieja: una la prueba igual que dos."""
    assert v._is_very_legit_profile(_sig(fotos=1, dias=400), None, "Ana", None)[0]
    assert v._is_very_legit_profile(_sig(fotos=3, dias=400), None, "Ana", None)[0]


def test_sin_ninguna_foto_no():
    assert not v._is_very_legit_profile(_sig(fotos=0), None, "Ana", None)[0]


def test_una_foto_reciente_tampoco():
    """Lo que importa no es la foto, es que la cuenta tenga historia."""
    assert not v._is_very_legit_profile(_sig(fotos=1, dias=30), None, "Ana", None)[0]


def test_un_nombre_en_otro_alfabeto_sigue_pasando_por_el_gate():
    assert not v._is_very_legit_profile(_sig(), None, "李大哥", None)[0]


def test_sin_telethon_no_se_libra_nadie():
    """Sin señales no se puede afirmar que el perfil sea legítimo."""
    assert not v._is_very_legit_profile(None, "ana", "Ana", None)[0]


# ------------------------------------------- «sin username» no es señal fuerte

def test_no_tener_username_no_es_senal_fuerte():
    """El 29 % de los miembros de Windows 11 no tiene: con eso no se manda a nadie
    al plazo de 30 minutos."""
    assert v.REASON_NO_USERNAME not in v._STRONG_SUSP_REASONS


@pytest.mark.parametrize("razon", ["REASON_NO_PHOTO", "REASON_RECENT_ACCOUNT",
                                   "REASON_NON_LATIN_NAME", "REASON_NON_LATIN_USERNAME"])
def test_las_que_si_son_fuertes_siguen_siendolo(razon):
    assert getattr(v, razon) in v._STRONG_SUSP_REASONS


def test_solo_sin_username_no_da_el_tier_duro():
    susp, razones = v._is_suspicious_profile(_sig(), None, "mario", None)
    assert susp, "sigue siendo sospechoso a efectos de registro"
    fuertes = [c for c, _ in razones if c in v._STRONG_SUSP_REASONS]
    assert not fuertes, "no debería haber ninguna señal fuerte aquí"


def test_sin_foto_si_da_el_tier_duro():
    susp, razones = v._is_suspicious_profile(_sig(fotos=0), None, "Ana", None)
    fuertes = [c for c, _ in razones if c in v._STRONG_SUSP_REASONS]
    assert fuertes, "no tener foto sí es una señal fuerte"


def test_el_flujo_degrada_el_tier_cuando_no_hay_senal_fuerte():
    """La costura: si alguien quita esta criba, «sin username» vuelve a mandar al
    29 % de la gente al plazo de 30 minutos."""
    from pathlib import Path
    fuente = Path("src/verification.py").read_text()
    i = fuente.index("suspicious, susp_reasons = _is_suspicious_profile")
    bloque = fuente[i:i + 1200]
    assert "_STRONG_SUSP_REASONS" in bloque
    assert "suspicious = False" in bloque


def test_quien_no_se_libra_sigue_verificandose():
    """No se abre la mano: sin señales fuertes se pasa al tier NORMAL, no se salta
    la verificación."""
    from pathlib import Path
    fuente = Path("src/verification.py").read_text()
    i = fuente.index("suspicious, susp_reasons = _is_suspicious_profile")
    bloque = fuente[i:i + 1200]
    assert "tier normal" in bloque
