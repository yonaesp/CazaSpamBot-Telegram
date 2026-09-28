"""Bio o canal personal escritos en un alfabeto no permitido = ban, sin excepciones.

Decisión del admin (28-sep-2026), tras «Mahmoud Rashed» (Windows 10): nombre en
latino, pero bio y canal («برامج و العاب», programas y juegos) en árabe. Entró
saltándose hasta la verificación (3 fotos, 650 días) y su único mensaje fue un
comentario cebo para llevar gente al canal. El detector del canal le daba 40/100.
"""
from __future__ import annotations

from types import SimpleNamespace

from src import verification as v


def _sig(bio=None, canal=None, fotos=3, dias=650):
    return SimpleNamespace(bio=bio, personal_channel_title=canal, photo_count=fotos,
                           account_age_days=dias, personal_channel_id=None)


def _ban(sig, nombre="Mahmoud", apellido="Rashed", usuario="Ma7sx", permitidos=None):
    return v._is_obvious_spam_profile(sig, usuario, nombre, apellido,
                                      allowed_scripts=permitidos)


def test_el_caso_real():
    ok, razones = _ban(_sig("صلي علي النبي و تبسم 🥺❤️", "برامج و العاب"),
                       nombre="Mahmoudㅤ")
    assert ok and razones[-1][0] == v.REASON_PROFILE_TEXT_SCRIPT


def test_basta_con_el_canal_o_con_la_bio():
    assert _ban(_sig(canal="برامج و العاب"))[0]
    assert _ban(_sig(bio="صلي علي النبي و تبسم"))[0]


def test_sin_excepciones_ni_para_cuentas_antiguas_con_foto():
    assert _ban(_sig(bio="صلي علي النبي و تبسم", fotos=9, dias=3000))[0]


def test_anti_fp():
    """Adornos sueltos, pocas letras, textos mezclados y canales en español: nada."""
    for bio, canal in (("Informático ツ Madrid", None), ("Paz سل", None),
                       ("Люблю Windows", None), (None, "Trucos de Windows"),
                       ("Ingeniero. Vivo en Madrid.", "Mi canal ♛")):
        assert not _ban(_sig(bio, canal), nombre="Ana", apellido="López",
                        usuario="ana")[0], (bio, canal)


def test_respeta_los_alfabetos_del_chat():
    """Un grupo que permita árabe no se autodestruye."""
    assert not _ban(_sig(bio="صلي علي النبي و تبسم"), permitidos=["latin", "arabic"])[0]


def test_sin_telethon_no_hay_bio_ni_canal_que_mirar():
    assert not _ban(None)[0]
