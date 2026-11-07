"""Bots de spam: adelantarse a que escriban en otro grupo y banear a quien los llama.

Pedido del admin (7-nov-2026), tras el caso de Windows 11: «Chelsea» (8686388890),
nueva, escribió «@amsoslbot @ybjsibot @tbjsibot» (61715) y los tres bots, con el
nombre en chino, contestaron en el mismo segundo (61716-61718). «Si alguien mencionó
a esos bots, que se banee a esa persona y a los bots mencionados antes de que lleguen
incluso a escribir».
"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from src import autoaprendizaje, bots_invitados, destinos, handlers
from src.detectors import url_blocklist
from tests.test_aviso_accion import ADMIN_DM, CHAT, _ctx, _Telegram
from tests.test_protecciones_criticas import _cfg, _db

CHELSEA, LLAMADA = 8686388890, 61715
TEXTO = "@amsoslbot @ybjsibot @tbjsibot"
BOTS = [(9256283624, "amsoslbot", 61718), (9298248354, "ybjsibot", 61717), (9298708505, "tbjsibot", 61716)]
NOMBRE = "新手也能做一单500"
OTROS = (-100100 - 1, -100100 - 2)


class _Grupos(_Telegram):
    """Además: quién es miembro de cada grupo (un bot que metió un admin)."""

    def __init__(self, mensajes, miembros=()):
        super().__init__(mensajes)
        self.miembros = set(miembros)

    async def get_chat_member(self, chat_id, user_id):
        return NS(status="member" if (chat_id, user_id) in self.miembros or user_id == CHELSEA else "left")


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    bots_invitados._actuados.clear()
    bots_invitados._llamadas.clear()
    bots_invitados._miembro_cache.clear()
    monkeypatch.setattr(handlers.notify_prefs, "sin_sonido", lambda db, importante: True)


@pytest.fixture
def db(tmp_path):
    d = _db(tmp_path, n_chats=3)
    d.upsert_bot_chat(CHAT, "💻 Windows 11 en Español", "supergroup", True, True, True, username="Windows11ESP")
    d.record_message(CHAT, CHELSEA, None)
    d.guardar_mensaje_reciente(CHAT, CHELSEA, LLAMADA, TEXTO)
    return d


def _cfg_latin(**kw):
    return _cfg(admin_notify_chat_id=ADMIN_DM, allowed_scripts=["latin"], is_moderated=lambda cid: True,
                moderated_chat_ids_set=frozenset(), **kw)


async def _contestan(ctx, db, cfg, bots=BOTS, nombre=NOMBRE, llamante=CHELSEA):
    for bot_id, user, mid in bots:
        await handlers._banear_bot_invitado(
            ctx, db, cfg, chat_id=CHAT, chat_title=None, message_id=mid,
            bot_user=NS(id=bot_id, username=user, first_name=nombre), llamado_por=llamante,
            texto=nombre, via="mtproto")


def _filas(db, regla):
    with db._cur() as c:
        return c.execute("SELECT chat_id, user_id, mode FROM moderation_log WHERE rule=?", (regla,)).fetchall()


@pytest.mark.asyncio
async def test_el_caso_real_banea_a_la_llamante_y_a_los_bots_en_todos_los_grupos(db, monkeypatch):
    monkeypatch.setattr(handlers, "_trust_score_cached", lambda *a: 5)
    cfg = _cfg_latin()
    tg = _Grupos([LLAMADA, 61716, 61717, 61718])
    await _contestan(_ctx(db, cfg, tg), db, cfg)
    for bot_id, user, _mid in BOTS:
        assert {(c, u) for c, u in tg.baneados if u == bot_id} == {(CHAT, bot_id), *((o, bot_id) for o in OTROS)}
        assert destinos.clave_bot(user) in destinos.fichados(db)
    assert len(_filas(db, "bot_de_spam_preventivo")) == 6
    assert len(_filas(db, "llama_bot_de_spam")) == 1, "a la llamante se la banea una vez, no una por bot"
    assert db.is_banned(CHELSEA)
    assert LLAMADA in tg.copiados, "el aviso del ban de la llamante lleva su mensaje"


@pytest.mark.asyncio
async def test_si_la_llamante_ya_esta_baneada_no_se_repite(db, monkeypatch):
    monkeypatch.setattr(handlers, "_trust_score_cached", lambda *a: 5)
    db.add_ban(user_id=CHELSEA, reason="x", rule="external_mention_or_link", banned_in_chat=CHAT, federated=True)
    cfg = _cfg_latin()
    tg = _Grupos([61716, 61717, 61718])
    await _contestan(_ctx(db, cfg, tg), db, cfg)
    assert _filas(db, "llama_bot_de_spam") == []
    assert len(_filas(db, "bot_de_spam_preventivo")) == 6


@pytest.mark.asyncio
async def test_un_veterano_que_llama_a_un_bot_de_spam_no_cae(db, monkeypatch):
    monkeypatch.setattr(handlers, "_trust_score_cached", lambda *a: 85)
    cfg = _cfg_latin()
    tg = _Grupos([61716])
    await _contestan(_ctx(db, cfg, tg), db, cfg, bots=BOTS[:1])
    assert not db.is_banned(CHELSEA)
    assert len(_filas(db, "bot_de_spam_preventivo")) == 2, "el bot sí se banea en los demás"


@pytest.mark.asyncio
async def test_un_bot_sin_senales_solo_se_banea_aqui(db, monkeypatch):
    """Un bot de verdad (nombre latino, uno solo, quien lo llama no está baneado)."""
    monkeypatch.setattr(handlers, "_trust_score_cached", lambda *a: 5)
    cfg = _cfg_latin()
    tg = _Grupos([500])
    await _contestan(_ctx(db, cfg, tg), db, cfg, bots=[(777, "traductor_es_bot", 500)], nombre="Traductor")
    assert tg.baneados == [(CHAT, 777)]
    assert destinos.clave_bot("traductor_es_bot") not in destinos.fichados(db)
    assert not db.is_banned(CHELSEA)


@pytest.mark.asyncio
async def test_donde_lo_metio_un_admin_se_queda(db, monkeypatch):
    monkeypatch.setattr(handlers, "_trust_score_cached", lambda *a: 85)
    cfg = _cfg_latin()
    tg = _Grupos([61716], miembros={(OTROS[0], BOTS[0][0])})
    await _contestan(_ctx(db, cfg, tg), db, cfg, bots=BOTS[:1])
    assert (OTROS[0], BOTS[0][0]) not in tg.baneados
    assert (OTROS[1], BOTS[0][0]) in tg.baneados


@pytest.mark.asyncio
async def test_en_shadow_no_banea_de_antemano(db, monkeypatch):
    monkeypatch.setattr(handlers, "_trust_score_cached", lambda *a: 85)
    cfg = _cfg_latin(shadow=True)
    tg = _Grupos([61716])
    await _contestan(_ctx(db, cfg, tg), db, cfg, bots=BOTS[:1])
    assert tg.baneados == []
    assert {f["mode"] for f in _filas(db, "bot_de_spam_preventivo")} == {"shadow"}


def test_mencionar_un_bot_fichado_es_un_ban():
    fichados = frozenset({"t.me/tbjsibot"})
    msg = NS(text="mira @tbjsibot gana 500", caption=None, entities=[], caption_entities=[])
    hit = url_blocklist.check(msg, [], is_first_msg=False, fichados=fichados)
    assert (hit.rule, hit.score) == ("bot_fichado", 100) and hit.payload["bots"] == ["@tbjsibot"]
    # La ruta de bots miembro no lo mira: un bot de moderación que cita al spammer no es spam.
    assert not url_blocklist.check(msg, [], is_first_msg=False, fichados=fichados, menciones=False)


def test_los_bots_conocidos_nunca_se_fichan():
    assert destinos.clave_bot("@BotFather") is None
    assert destinos.clave_bot("MissRose_bot") is None
    assert destinos.clave_bot("CazaSpamBot") is None
    assert destinos.clave_bot("hola") is None
    assert destinos.clave_bot("@TbjsiBot") == "t.me/tbjsibot"


def test_un_ban_por_contenido_ficha_los_bots_que_mencionaba(db):
    assert destinos.aprender_bots_de_ban(db, CHELSEA, TEXTO, "external_mention_or_link") == [
        "amsoslbot", "tbjsibot", "ybjsibot"]
    assert destinos.aprender_bots_de_ban(db, 1, "@otrobot", "manual_admin_ban") == []
    assert destinos.aprender_bots_de_ban(db, 1, "@otrobot", "obvious_spam_profile") == []


def test_desbanear_olvida_el_bot(db):
    destinos.fichar_bot(db, "tbjsibot", 9298708505, "bot_invitado")
    destinos.olvidar(db, 9298708505)
    assert "t.me/tbjsibot" not in destinos.fichados(db)


def test_las_reglas_que_fichan_bots_incluyen_las_de_contenido():
    """Si `autoaprendizaje` gana una regla de contenido, también ficha bots."""
    assert autoaprendizaje._REGLAS_DE_CONTENIDO <= destinos.REGLAS_QUE_FICHAN_BOTS


def test_anotar_llamada_cuenta_bots_distintos_en_la_ventana():
    assert len(bots_invitados.anotar_llamada(CHAT, 1, 10, "a_bot", ahora=0)) == 1
    assert len(bots_invitados.anotar_llamada(CHAT, 1, 10, "a_bot", ahora=1)) == 1
    assert len(bots_invitados.anotar_llamada(CHAT, 1, 11, "b_bot", ahora=2)) == 2
    assert len(bots_invitados.anotar_llamada(CHAT, 1, 12, "c_bot", ahora=500)) == 1
