"""«Este es mi número de otra app, escríbeme ahí»: el hueco que obligaba a borrar a mano.

Caso real (07/08/2026, Windows 10). Cuenta nueva, catorce minutos después de entrar,
primer y único mensaje. Ni enlace, ni @mención, ni alfabeto raro, y en español
correcto: ningún detector tenía nada que mirar. Estuvo hora y cuarto en el grupo
hasta que un admin lo borró y baneó a mano.

Los tests que de verdad importan aquí son los NEGATIVOS: el mensaje legítimo que más
se parece a este spam es «mi whatsapp es 600123456», y ese no puede caer.
"""
from types import SimpleNamespace

import pytest

from src.detectors import offplatform_contact as det


def _msg(texto):
    return SimpleNamespace(text=texto, caption=None)


# El mensaje real, tal cual quedó guardado en la base de datos.
REAL = ("Este es mi número de Zangi; puedes escribirme ahí ahora mismo 👉👉 7702361204\n"
        "Zangi 👉\n\n"
        "Cariño, este es mi nuevo número de Zangi: 3476746619. Escríbeme ahora 💞❤️❤️")


def test_el_caso_real_se_caza():
    hit = det.check(_msg(REAL), is_first_msg=True)
    assert hit, "el mensaje que hubo que borrar a mano seguiría pasando"
    assert hit.rule == "offplatform_contact"
    assert hit.score >= 100, f"score {hit.score}: no llegaría a ban en primer mensaje"


def test_las_tres_senales_de_apoyo_estan_presentes_en_el_caso_real():
    assert det.check(_msg(REAL), is_first_msg=True).payload["signals"] == 3


@pytest.mark.parametrize("texto", [
    # El ancla completa (app + teléfono) pero sin ningún apoyo: es exactamente el
    # mensaje legítimo que más se parece al spam. No puede caer.
    "Mi whatsapp es 600123456 por si alguien lo necesita",
    "Te paso mi Skype: 612345678",
    # Sin teléfono no hay ancla.
    "¿Alguien usa Signal? Me han dicho que va mejor que WhatsApp",
    "Pásame tu whatsapp y lo vemos",
    # Sin app no hay ancla, aunque haya número y prisa.
    "Llama al 900123456, es el soporte oficial de Microsoft",
    "Mi número es 654321987, escríbeme ahora",
    # CTA suelta: en un grupo de ayuda la dice todo el mundo.
    "Escríbeme por privado y te lo explico",
    "Contáctame ahora si sigues con el problema",
    # Números que no son teléfonos.
    "La build 22621.1234 me da pantallazo azul en Skype",
    "El disco va a 0.1 MB/s con WhatsApp abierto",
    # Trato afectivo sin nada más.
    "Cariño, ¿me echas una mano con el Windows?",
])
def test_no_dispara_con_mensajes_legitimos(texto):
    """FP > FN: aquí el precio de equivocarse es expulsar a alguien que pedía ayuda."""
    assert not det.check(_msg(texto), is_first_msg=True), f"falso positivo: {texto!r}"


def test_el_ancla_sola_nunca_decide():
    """Doctrina del proyecto: ninguna señal decide sola. Sin apoyo no se emite,
    ni siquiera con un score que daría para mute."""
    assert not det.check(_msg("Mi Botim es 5551234567"), is_first_msg=True)


def test_con_ancla_basta_un_apoyo():
    hit = det.check(_msg("Mi Botim es 5551234567, escríbeme ahí"), is_first_msg=False)
    assert hit and hit.payload["signals"] == 1


def test_el_primer_mensaje_refuerza_pero_no_decide():
    """Si el primer mensaje decidiera, bastaría con esperar un día para colarlo."""
    texto = "Mi Botim es 5551234567, escríbeme ahí"
    assert det.check(_msg(texto), is_first_msg=True).score > det.check(_msg(texto)).score
    assert det.check(_msg("Hola buenas"), is_first_msg=True) == det.check(_msg("Hola buenas"))


def test_los_corazones_cuentan_como_gancho():
    """El timo romántico no siempre escribe «cariño», pero siempre pone corazones."""
    hit = det.check(_msg("Mi Zangi: 5551234567 ❤️❤️"), is_first_msg=True)
    assert hit, "dos corazones + número de otra app deberían bastar"


def test_un_corazon_suelto_no_basta():
    assert not det.check(_msg("Mi Zangi es 5551234567 ❤️"), is_first_msg=True)


def test_tambien_en_ingles():
    hit = det.check(_msg("Hi darling, this is my new number on Botim: 5551234567, "
                         "write me there"), is_first_msg=True)
    assert hit and hit.payload["signals"] == 3


def test_mensaje_vacio_no_revienta():
    assert not det.check(_msg(None))
    assert not det.check(SimpleNamespace(text=None, caption="   "))
