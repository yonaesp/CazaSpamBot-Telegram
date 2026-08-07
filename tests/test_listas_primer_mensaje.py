"""CAS y lols.bot se consultan también en los primeros mensajes, no solo al entrar.

Caso real (agosto 2026): un spammer entró el día 1, cuando lols.bot todavía no lo
tenía fichado, así que la comprobación del join no sirvió de nada. Escribió el día
3, y para entonces lols YA lo tenía: lo marcó a las 08:16 UTC y nosotros baneamos a
las 08:27, once minutos tarde y por el idioma del mensaje, no por la lista.

Consultando también al escribir, ese caso cae por lols con cualquier texto, aunque
escriba en español perfecto.
"""
from pathlib import Path


def test_las_listas_se_consultan_en_el_primer_mensaje():
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def on_message(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    assert "lols_det.check" in cuerpo, (
        "on_message no consulta lols: un spammer fichado DESPUÉS de entrar se cuela")
    assert "cas_det.check" in cuerpo, "on_message no consulta CAS"


def _bloque() -> str:
    """El bloque completo, delimitado por los marcadores reales del fichero.

    Recortar por un número fijo de caracteres dejaba fuera la mitad y el test
    medía menos de lo que creía.
    """
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("# 3d ter) LISTAS EXTERNAS")
    return fuente[i:fuente.index("# 3e)", i)]


def test_solo_en_los_primeros_mensajes():
    """Quien ya participa no se re-consulta: el coste queda acotado a recién llegados."""
    bloque = _bloque()
    assert "if is_first" in bloque, "se consultaría en CADA mensaje de cualquiera"
    assert "is_whitelisted" in bloque, "consultaría también a los usuarios inmunes"


def test_hay_cache_para_no_repetir_llamadas():
    """CAS ya cachea; lols no tenía caché propia y aquí se llamaría varias veces
    dentro de los primeros mensajes del mismo usuario."""
    assert "_lols_cache" in _bloque()


def test_son_reglas_duras_asi_que_el_trust_no_las_anula():
    """Un veterano cuya cuenta acabe fichada por lols debe caer igual: si el trust
    las anulara, una cuenta robada con historial seguiría spameando."""
    from src.handlers import HARD_RULES_BAN
    assert "cas_match" in HARD_RULES_BAN and "lols_match" in HARD_RULES_BAN


def test_un_fallo_de_red_no_tumba_la_moderacion():
    """Las listas son un extra: si no responden, el mensaje se sigue evaluando."""
    assert _bloque().count("except Exception") >= 2, "un fallo de red propagaría"
