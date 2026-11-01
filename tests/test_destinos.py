"""Destinos fichados: el bot aprende adónde llevan los enlaces del spam baneado (L50).

El admin pidió banear «por tipo de enlace, tipo t.me/*». En el barrido del 31-oct, 9
veteranos legítimos llevan un t.me en la bio, así que se aprende el destino concreto
(dominio, canal o invitación) y nunca una plataforma compartida.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from telegram import MessageEntity

from src import destinos
from src.db import DB
from src.detectors import bio_spam
from src.detectors import url_blocklist as ub

BITNEST = "BITNEST https://bitnest.me/QSZPR"   # la cuenta robada: 15 en bio_spam
CHINO = "付费广告 https://t.me/ZOGJ001"


@pytest.mark.parametrize("texto,claves", [
    (BITNEST, ["bitnest.me"]),
    (CHINO, ["t.me/zogj001"]),
    ("Cursway → t.me/+3JVb6dw6WbI0ODk6", ["t.me/+3jvb6dw6wbi0odk6"]),
    ("https://t.me/joinchat/AbCd123 y t.me/+abcd123", ["t.me/+abcd123"]),  # la misma invitación
    ("telegram.me/Canal?start=1", ["t.me/canal"]),
    ("😈Find here👉https://t.me/+M9MbBkVPxxwwZjhi💋", ["t.me/+m9mbbkvpxxwwzjhi"]),  # isabelle
    ("www.messbeard.es", ["messbeard.es"]),
    ("bbc.co.uk/news", ["bbc.co.uk"]),
    # Plataformas compartidas: nunca se fichan.
    ("https://www.youtube.com/@juanpesadolopez", []),
    ("https://sites.google.com/view/juanlgtr1", []),
    ("https://m.facebook.com/story.php?x=1", []),
    ("https://t.me/", []),
    # Sin esquema, sin www y sin ruta no es un enlace: «Hola.Que tal».
    ("Hola.Que tal", []),
    ("Limpiezasrelim.com", []),
])
def test_claves(texto, claves):
    assert destinos.claves(texto) == claves


def test_solo_fichan_los_bans_con_evidencia_de_spam(tmp_db):
    assert destinos.aprender_de_ban(tmp_db, 1, BITNEST, "manual_admin_ban") == 0  # puede ser por insultar
    assert destinos.aprender_de_ban(tmp_db, 1, "https://mi-web.es/", "warn_limit") == 0
    # Una estafa que cita un periódico: el periódico no es el spam.
    assert destinos.aprender_de_ban(tmp_db, 1, "como dice https://elpais.com/x", "investment_scam") == 0
    assert destinos.aprender_de_ban(tmp_db, 2, BITNEST, "cuenta_robada") == 1
    assert destinos.aprender_de_ban(tmp_db, 3, CHINO, "first_msg_media+link_target_spam") == 1
    assert tmp_db.destinos_fichados() == {"bitnest.me", "t.me/zogj001"}


def test_al_desbanear_se_olvida_lo_fichado_de_esa_cuenta(tmp_db):
    from src.federation import unfederate_ban
    destinos.aprender_de_ban(tmp_db, 2, BITNEST, "cuenta_robada")
    destinos.aprender_de_ban(tmp_db, 3, BITNEST + " " + CHINO, "bio_spam")
    bot = SimpleNamespace(unban_chat_member=_async_none)
    import asyncio
    asyncio.run(unfederate_ban(bot, tmp_db, 3, revoked_by=99, shadow=False))
    assert tmp_db.destinos_fichados() == {"bitnest.me"}  # sigue fichado por la cuenta 2


async def _async_none(**kw):
    return None


def test_bio_spam_suma_el_destino_fichado(tmp_db):
    assert not bio_spam.check(BITNEST, db=tmp_db, user_id=10)
    destinos.aprender_de_ban(tmp_db, 2, BITNEST, "cuenta_robada")
    hit = bio_spam.check("Gana dinero con BITNEST https://bitnest.me/ABCDE", db=tmp_db, user_id=10)
    assert hit and hit.score >= 60
    assert hit.payload["destinos_fichados"] == ["bitnest.me"]
    assert "bitnest.me" in hit.reason
    # Sin base, como antes.
    assert not bio_spam.check(BITNEST)


def test_una_web_comun_en_la_bio_de_un_spammer_no_marca_a_nadie(tmp_db):
    destinos.aprender_de_ban(tmp_db, 2, "Mis vídeos https://youtube.com/@spam " + BITNEST, "bio_spam")
    assert not bio_spam.check("Sígueme en https://youtube.com/@pepe", db=tmp_db, user_id=10)


def _msg(texto):
    m = MagicMock()
    m.text, m.caption, m.caption_entities = texto, None, None
    m.entities = [MessageEntity(type=MessageEntity.URL, offset=0, length=len(texto))]
    return m


def test_url_blocklist_caza_un_destino_fichado():
    fichados = frozenset({"bitnest.me", "t.me/zogj001"})
    assert ub.check(_msg("https://bitnest.me/XYZ"), [], True, fichados=fichados).score == 60
    assert ub.check(_msg("https://www.bitnest.me/"), [], False, fichados=fichados).score == 25
    assert ub.check(_msg("https://t.me/ZOGJ001"), [], True, fichados=fichados)
    assert not ub.check(_msg("https://t.me/otro_canal"), [], True, fichados=fichados)
    assert not ub.check(_msg("https://bitnest.me/XYZ"), [], True)  # sin fichados, como antes


def test_ultima_bio_vista(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    assert db.ultima_bio_vista(5) is None
    db.log_action(chat_id=-1, user_id=5, username=None, message_id=None, rule="bio_spam",
                  action="noop", score=70, mode="active", payload={"bio_preview": BITNEST})
    assert db.ultima_bio_vista(5) == BITNEST


# ------------------------------------------------- dónde se aprende (estructura)

def _llamadas(fichero: str, funcion: str) -> list[ast.Call]:
    tree = ast.parse(Path(fichero).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == funcion)
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call)]


def _nombres(llamadas) -> list[str]:
    return [ast.unparse(c.func) for c in llamadas]


def test_aprenden_el_ban_automatico_y_los_botones_de_revision():
    assert "destinos.aprender_de_ban" in _nombres(_llamadas("src/handlers.py", "_apply_action"))
    assert "destinos.aprender_de_ban" in _nombres(
        _llamadas("src/handlers.py", "on_pending_review_callback"))
    assert "destinos.aprender_de_ban" in _nombres(
        _llamadas("src/admin.py", "on_suspicious_review_callback"))
    assert "destinos.olvidar" in _nombres(_llamadas("src/federation.py", "unfederate_ban"))


def test_todas_las_llamadas_a_url_blocklist_pasan_los_fichados():
    tree = ast.parse(Path("src/handlers.py").read_text(encoding="utf-8"))
    llamadas = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and ast.unparse(n.func) == "url_det.check"]
    assert len(llamadas) == 4
    assert all(any(k.arg == "fichados" for k in c.keywords) for c in llamadas)
