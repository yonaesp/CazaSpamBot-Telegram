"""El mismo mensaje, a la vez, en varios de nuestros grupos.

Aprovecha lo que casi ningún bot tiene y este sí: la federación. Quien modera un
grupo no puede ver esto; quien modera cuatro, sí. Una persona escribe donde tiene
el problema; un anuncio se reparte por todos.

Lo bueno de la señal es que **no mira el contenido**: un spam nuevo, en un idioma
que no está en las listas y con vocabulario que nadie ha visto, sigue siendo el
mismo texto repetido. Caza lo que las listas todavía no saben cazar.

Los tests que mandan son los negativos, como siempre: quien pregunta lo mismo en
dos grupos parecidos (Windows 10 y Windows 11) tiene un problema de verdad, no una
campaña.
"""
import time

from src.db import DB
from src.detectors import cross_post as det

TEXTO = "Buenas, tengo un problema con la activacion de Windows y no encuentro la licencia"


def _db(tmp_path) -> DB:
    db = DB(str(tmp_path / "t.db"))
    for cid, nombre in ((-100, "W10"), (-200, "W11"), (-300, "Domótica"), (-400, "W12")):
        db.upsert_bot_chat(cid, nombre, "supergroup", True, True, True)
    return db


def _escribe(db, chat_id, user_id, texto, cuando=None):
    db.record_message(chat_id, user_id, None)
    db.update_last_message(chat_id, user_id, 1, texto)
    if cuando is not None:
        with db._cur() as c:
            c.execute("UPDATE seen_users SET last_msg_ts=? WHERE chat_id=? AND user_id=?",
                      (cuando, chat_id, user_id))


def test_el_mismo_texto_en_tres_grupos_salta(tmp_path):
    db = _db(tmp_path)
    for cid in (-100, -200, -300):
        _escribe(db, cid, 7, TEXTO)
    hit = det.check(db, -300, 7, TEXTO)
    assert hit and hit.rule == "cross_post"
    assert hit.payload["chats"] == 3


def test_en_dos_grupos_no_basta(tmp_path):
    """Alguien con un problema de verdad lo pregunta en el de Windows 10 y en el de
    Windows 11, que se parecen. Con dos era demasiado fácil equivocarse."""
    db = _db(tmp_path)
    for cid in (-100, -200):
        _escribe(db, cid, 7, TEXTO)
    assert not det.check(db, -200, 7, TEXTO)


def test_personas_distintas_no_cuentan(tmp_path):
    """Tres usuarios diciendo lo mismo no es una campaña, es un grupo de soporte."""
    db = _db(tmp_path)
    for cid, uid in ((-100, 1), (-200, 2), (-300, 3)):
        _escribe(db, cid, uid, TEXTO)
    assert not det.check(db, -300, 3, TEXTO)


def test_repetirse_en_el_MISMO_grupo_no_cuenta(tmp_path):
    """De eso ya se ocupa el antiflood; aquí la señal es el reparto."""
    db = _db(tmp_path)
    for _ in range(5):
        _escribe(db, -100, 7, TEXTO)
    assert not det.check(db, -100, 7, TEXTO)


def test_fuera_de_la_ventana_no_cuenta(tmp_path):
    """Preguntar lo mismo en tres grupos con una semana de diferencia es razonable."""
    db = _db(tmp_path)
    viejo = time.time() - det.VENTANA_S - 600
    for cid in (-100, -200):
        _escribe(db, cid, 7, TEXTO, cuando=viejo)
    _escribe(db, -300, 7, TEXTO)
    assert not det.check(db, -300, 7, TEXTO)


def test_los_mensajes_cortos_se_ignoran(tmp_path):
    """«gracias», «sí», «alguien?»: se repiten solos todo el tiempo."""
    db = _db(tmp_path)
    for cid in (-100, -200, -300, -400):
        _escribe(db, cid, 7, "gracias")
    assert not det.check(db, -300, 7, "gracias")


def test_cambiar_mayusculas_o_invisibles_no_sirve(tmp_path):
    """Se compara el texto NORMALIZADO, el mismo del clasificador."""
    db = _db(tmp_path)
    _escribe(db, -100, 7, TEXTO)
    _escribe(db, -200, 7, TEXTO.upper())
    _escribe(db, -300, 7, TEXTO.replace(" ", " ​"))
    assert det.check(db, -300, 7, TEXTO)


def test_no_decide_solo(tmp_path):
    """Ninguna señal decide sola: no llega a BAN_SCORE por sí misma."""
    assert det.SCORE < 100


def test_un_fallo_de_la_consulta_no_tumba_la_moderacion(tmp_path):
    class Rota:
        def chats_con_el_mismo_texto(self, *a, **k):
            raise RuntimeError("base ocupada")
    assert not det.check(Rota(), -100, 7, TEXTO)


def test_texto_vacio(tmp_path):
    db = _db(tmp_path)
    assert not det.check(db, -100, 7, "")
    assert not det.check(db, -100, 7, None)
