"""Oleadas (varias cuentas, mismo texto) y calentamiento (relleno y luego enlace)."""
from __future__ import annotations

import time

from src.detectors import calentamiento, oleada

TEXTO = ("Hola a todos, tengo un trabajo desde casa que me deja un dinero extra cada "
         "semana y quiero compartirlo con vosotros")


# ── Oleada ───────────────────────────────────────────────────────────────────

def _guardar(db, chat, uid, msg_id, texto):
    db.guardar_mensaje_reciente(chat, uid, msg_id, texto)


def test_dos_cuentas_nuevas_con_el_mismo_texto_suman(tmp_db):
    _guardar(tmp_db, -1, 100, 1, TEXTO)
    hit = oleada.check(tmp_db, 200, TEXTO.upper() + " 😀", is_first_msg=True)
    assert hit.rule == "oleada" and hit.score == oleada.SCORE
    assert hit.payload["cuentas"] == 2


def test_no_decide_sola():
    assert oleada.SCORE < 40  # por debajo del mute por defecto


def test_veterano_no_cuenta(tmp_db):
    _guardar(tmp_db, -1, 100, 1, TEXTO)
    assert not oleada.check(tmp_db, 200, TEXTO, is_first_msg=False)


def test_texto_corto_no_cuenta(tmp_db):
    _guardar(tmp_db, -1, 100, 1, "Hola a todos, buenas tardes")
    assert not oleada.check(tmp_db, 200, "Hola a todos, buenas tardes", is_first_msg=True)


def test_la_misma_persona_no_es_oleada(tmp_db):
    _guardar(tmp_db, -1, 200, 1, TEXTO)
    assert not oleada.check(tmp_db, 200, TEXTO, is_first_msg=True)


def test_texto_parecido_pero_distinto_no_cuenta(tmp_db):
    _guardar(tmp_db, -1, 100, 1, "Alguien sabe por qué Windows 11 no me deja instalar la "
                                  "actualización de octubre en un portátil viejo")
    assert not oleada.check(tmp_db, 200, "Alguien sabe por qué Windows 10 no me deja abrir "
                                          "la tienda de Microsoft después de reiniciar", True)


def test_fuera_de_la_hora_no_cuenta(tmp_db):
    _guardar(tmp_db, -1, 100, 1, TEXTO)
    assert not oleada.check(tmp_db, 200, TEXTO, True, ahora=time.time() + 2 * 3600)


# ── Calentamiento ────────────────────────────────────────────────────────────

def _recien_llegado(db, chat=-1, uid=300, dias=1):
    db.record_join(chat, uid, "x", join_ts=time.time() - dias * 86400)


def _previos(db, textos, chat=-1, uid=300):
    for i, tx in enumerate(textos, start=1):
        db.guardar_mensaje_reciente(chat, uid, i, tx)


def test_relleno_y_luego_enlace_suma(tmp_db):
    _recien_llegado(tmp_db)
    _previos(tmp_db, ["hi", "ok", "jaja", "nice group"])
    hit = calentamiento.check(tmp_db, -1, 300, 99, msg_count=5, is_first_msg=False,
                              hay_invitacion=True)
    assert hit.rule == "calentamiento" and hit.score == calentamiento.SCORE


def test_sin_enlace_no_pasa_nada(tmp_db):
    _recien_llegado(tmp_db)
    _previos(tmp_db, ["hi", "ok", "jaja"])
    assert not calentamiento.check(tmp_db, -1, 300, 99, 4, False, hay_invitacion=False)


def test_si_antes_hablo_de_verdad_no_cuenta(tmp_db):
    _recien_llegado(tmp_db)
    _previos(tmp_db, ["hola", "alguien sabe cómo quitar el bloqueo de BitLocker sin la clave"])
    assert not calentamiento.check(tmp_db, -1, 300, 99, 4, False, True)


def test_en_los_primeros_mensajes_no_aplica(tmp_db):
    _recien_llegado(tmp_db)
    _previos(tmp_db, ["hi", "ok"])
    assert not calentamiento.check(tmp_db, -1, 300, 99, 3, True, True)


def test_quien_lleva_muchos_mensajes_no_cuenta(tmp_db):
    _recien_llegado(tmp_db)
    _previos(tmp_db, ["hi", "ok"])
    assert not calentamiento.check(tmp_db, -1, 300, 99, 20, False, True)


def test_sin_entrada_vista_no_cuenta(tmp_db):
    _previos(tmp_db, ["hi", "ok"])
    assert not calentamiento.check(tmp_db, -1, 300, 99, 4, False, True)


def test_entro_hace_mas_de_una_semana_no_cuenta(tmp_db):
    _recien_llegado(tmp_db, dias=10)
    _previos(tmp_db, ["hi", "ok"])
    assert not calentamiento.check(tmp_db, -1, 300, 99, 4, False, True)


def test_solo_cuenta_una_invitacion_privada():
    """Simulación del 29-oct: «buenas», «gracias!!», «ok» y luego un grupo público
    (t.me/WindowsAyuda) es gente normal; con esta señal pasaba de silencio a expulsión."""
    assert calentamiento.es_invitacion(["https://t.me/+Ab3dEfGhIjk"])
    assert calentamiento.es_invitacion(["t.me/joinchat/AAAAAEx"])
    assert calentamiento.es_invitacion(["https://telegram.me/+xyz"])
    assert not calentamiento.es_invitacion(["https://t.me/WindowsAyuda"])
    assert not calentamiento.es_invitacion(["https://t.me/xataka/1234"])
    assert not calentamiento.es_invitacion(None)


def test_el_handler_le_pasa_solo_invitaciones():
    from pathlib import Path
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("calentamiento_det.check(")
    bloque = fuente[i - 600:i]
    assert "calentamiento_det.es_invitacion(" in bloque, (
        "calentamiento volvería a sumar con cualquier @ o grupo público")
