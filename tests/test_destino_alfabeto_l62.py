"""El enlace privado de la bio que lleva a un grupo en un alfabeto prohibido (L62).

Caso real (12-nov-2026, Windows 10): entró con la bio «赚钱进群了解https://t.me/+… 业务员@MY…»,
cuyo enlace lleva a «公群 2714 -墨颜集团色料代收 押金28888U». Ni la bio ni el destino
contaron como «escritos en chino» y la cuenta fue a revisión humana; la baneó el primer
mensaje, 19 minutos después de entrar, y el aviso de revisión siguió pidiendo una
decisión 95 minutos más.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest

from src import barrido_bios, federation, handlers, link_reader, recien_llegados, revisiones, verification
from src.db import DB

CHAT = -1001008178265
BIO = "赚钱进群了解https://t.me/+0bXkM6iJhUQ1ZWEx 业务员@MY1588888"
TITULO = "公群 2714 -墨颜集团色料代收 押金28888U"
SRC = Path(__file__).resolve().parent.parent / "src"


# ------------------------------------------------------------ medir el alfabeto

def test_las_cifras_no_hacen_decorativo_un_texto():
    """Para UTS#39 las cifras son «confundibles con el latín»: bastaba un «28888U»."""
    assert verification._is_decorative_mix(TITULO) is False
    assert verification._is_decorative_mix("业务员 MY1588888") is False
    # Lo decorativo de verdad lo sigue siendo, con cifras o sin ellas.
    assert verification._is_decorative_mix("๓คгς๏รקg24") is True
    assert verification._is_decorative_mix("ᏙᎪᏢᎬᎡՏᎬХͲᎡᎬᎷ") is True


@pytest.mark.parametrize("texto", [
    BIO,
    TITULO,
    "付费广告 https://t.me/ZOGJ001",
    "https://t.me/+M9nuR4dM5u1iZTFi ←进群赚钱 新手也能日赚8OOO 秒下款",
])
def test_textos_reales_escritos_en_chino(texto):
    hit = verification._texto_en_otro_alfabeto(texto, ["latin"])
    assert hit and hit[0] == "han"


@pytest.mark.parametrize("texto", [
    "Люблю Windows https://t.me/micanal",      # mezcla idiomas: el enlace no cambia nada
    "Me gusta Windows 11 ツ @pepe_1234",        # un adorno y un @ no son escribir en otro alfabeto
    "https://t.me/+abcDEF123 @soporte_bot",    # solo enlace y @: no hay texto que medir
    "Familia García",
    "Soporte 24/7: escribe a @admin_grupo o entra en t.me/grupo",
])
def test_lo_que_no_esta_en_otro_alfabeto(texto):
    assert verification._texto_en_otro_alfabeto(texto, ["latin"]) is None


def test_un_grupo_que_permite_el_chino_no_lo_marca():
    assert verification._texto_en_otro_alfabeto(BIO, ["latin", "han"]) is None
    assert verification._texto_en_otro_alfabeto(TITULO, ["latin", "han"]) is None


# -------------------------------------------- el destino del enlace de la bio

@pytest.fixture
def entorno(tmp_path, monkeypatch):
    db = DB(str(tmp_path / "t.db"))
    aplicar, revisar = AsyncMock(), AsyncMock()
    monkeypatch.setattr(handlers, "_apply_action", aplicar)
    monkeypatch.setattr(handlers, "_revision_humana", revisar)
    monkeypatch.setattr(handlers, "_se_modera", lambda db, cfg, cid: cid == CHAT)

    def poner(titulo, url="https://t.me/+0bXkM6iJhUQ1ZWEx"):
        async def leer(context, urls, **kw):
            return link_reader.Destino(titulo=titulo, descripcion="", url=url, chat_id=-100777)
        monkeypatch.setattr(link_reader, "leer", leer)
    return NS(db=db, aplicar=aplicar, revisar=revisar, poner=poner)


USER = NS(id=9255260498, username=None, first_name="Brianna")
SOLO_ENLACE = "https://t.me/+0bXkM6iJhUQ1ZWEx"


async def _revisar(e, permitidos=("latin",), bio=SOLO_ENLACE):
    cfg = NS(mode="active", shadow=False, allowed_scripts=list(permitidos))
    return await recien_llegados.revisar_destino_bio(
        NS(bot_data={}), e.db, cfg, CHAT, "Windows 10", USER, bio, "recien_llegados")


@pytest.mark.asyncio
async def test_destino_en_un_alfabeto_prohibido_es_ban(entorno):
    entorno.poner(TITULO)
    assert await _revisar(entorno) is True
    decision = entorno.aplicar.await_args.kwargs["decision"]
    assert decision.action == "ban" and decision.rule == "bio_spam" and decision.score == 100
    assert decision.payload["destino"] == TITULO and decision.payload["destino_alfabeto"] == "han"
    assert "han" in decision.reason
    entorno.revisar.assert_not_awaited()


@pytest.mark.asyncio
async def test_si_el_grupo_permite_ese_alfabeto_va_a_revision(entorno):
    entorno.poner(TITULO)
    assert await _revisar(entorno, permitidos=("latin", "han")) is False
    entorno.aplicar.assert_not_awaited()
    assert entorno.revisar.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("titulo", ["Familia García", "Windows ツ fans", "Amigos del 4PDA 2024"])
async def test_destino_en_alfabeto_permitido_sigue_yendo_a_revision(entorno, titulo):
    entorno.poner(titulo)
    assert await _revisar(entorno) is False
    entorno.aplicar.assert_not_awaited()
    assert entorno.revisar.await_count == 1


# ------------------------------------------------------- el barrido semanal

CFG_BARRIDO = NS(allowed_scripts=["latin"], mode="active", shadow=False)


@pytest.mark.asyncio
async def test_barrido_enlace_privado_a_un_grupo_en_otro_alfabeto(entorno):
    entorno.poner(TITULO)
    puntos, motivo = await barrido_bios._positivo(NS(bot_data={}), entorno.db, CFG_BARRIDO, CHAT, 8, SOLO_ENLACE)
    assert puntos == 60 and "han" in motivo


@pytest.mark.asyncio
async def test_barrido_un_canal_publico_en_otro_idioma_no_es_positivo(entorno):
    """Un veterano puede llevar en la bio su canal público, en el idioma que sea."""
    entorno.poner("Новости Windows", url="https://t.me/novosti_windows")
    assert await barrido_bios._positivo(
        NS(bot_data={}), entorno.db, CFG_BARRIDO, CHAT, 8, "Mi canal: https://t.me/novosti_windows") is None


# ------------------------------- el aviso de revisión se cierra al banear

def _aviso(db, user_id=USER.id, msg_id=77):
    revisiones.apuntar(db, NS(chat_id=14573395, message_id=msg_id), user_id, "🔍 <b>Usuario sospechoso</b>")


@pytest.mark.asyncio
async def test_el_ban_cierra_el_aviso_de_revision(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    _aviso(db)
    _aviso(db, user_id=5, msg_id=78)               # el de otra persona no se toca
    bot = AsyncMock()
    res = await federation.federate_ban(bot, db, user_id=USER.id, reason="x", rule="obvious_spam_profile",
                                        triggered_in_chat=CHAT, shadow=False)
    assert res == {CHAT: "ok"}
    (llamada,) = bot.edit_message_text.await_args_list
    kw = llamada.kwargs
    assert kw["chat_id"] == 14573395 and kw["message_id"] == 77
    assert kw["text"].startswith("🔍 <b>Usuario sospechoso</b>") and "baneado" in kw["text"].lower()
    assert "reply_markup" not in kw                # sin botones: ya no hay nada que decidir
    assert db.pop_revisiones(USER.id) == [] and len(db.pop_revisiones(5)) == 1


@pytest.mark.asyncio
async def test_en_shadow_o_sin_ban_aplicado_el_aviso_sigue_abierto(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    _aviso(db)
    bot = AsyncMock()
    await federation.federate_ban(bot, db, user_id=USER.id, reason="x", rule="lols_match",
                                  triggered_in_chat=CHAT, shadow=True)
    bot.ban_chat_member.side_effect = BadRequest("Not enough rights")
    await federation.federate_ban(bot, db, user_id=USER.id, reason="x", rule="lols_match",
                                  triggered_in_chat=CHAT, shadow=False)
    bot.edit_message_text.assert_not_awaited()
    assert len(db.pop_revisiones(USER.id)) == 1


@pytest.mark.asyncio
async def test_cerrar_un_aviso_nunca_tumba_el_ban(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    _aviso(db)
    bot = AsyncMock()
    bot.edit_message_text.side_effect = BadRequest("Message to edit not found")
    res = await federation.federate_ban(bot, db, user_id=USER.id, reason="x", rule="lols_match",
                                        triggered_in_chat=CHAT, shadow=False)
    assert res == {CHAT: "ok"} and db.is_banned(USER.id)
    bot.edit_message_text.side_effect = RuntimeError("otra cosa")
    _aviso(db)
    assert await revisiones.cerrar_por_ban(bot, db, USER.id, "lols_match") == 0


@pytest.mark.asyncio
async def test_el_aviso_de_sospechoso_queda_apuntado(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    bot = AsyncMock()
    bot.send_message.return_value = NS(chat_id=14573395, message_id=901)
    cfg = NS(admin_notify_chat_id=14573395)
    await verification._send_suspicious_review(
        NS(bot=bot), db, cfg, NS(id=CHAT, title="Windows 10"), USER,
        [("bio_enlace_privado", {"destino": "Familia García"})], None)
    (fila,) = db.pop_revisiones(USER.id)
    assert fila["aviso_msg_id"] == 901 and fila["texto"] == bot.send_message.await_args.kwargs["text"]


def _funciones(path: Path):
    for nodo in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield nodo


def _llamadas(fn) -> set[str]:
    nombres = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            nombres.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    return nombres


TECLADOS = {"build_review_keyboard", "build_muted_review_keyboard", "_rv_decide_row"}


def test_todo_aviso_con_los_botones_de_revision_se_apunta():
    """Un aviso nuevo con Permitir/Banear que no se apunte se quedaría abierto tras un ban."""
    vistos = []
    for path in sorted(SRC.glob("*.py")):
        for fn in _funciones(path):
            llamadas = _llamadas(fn)
            if llamadas & TECLADOS and "send_message" in llamadas:
                vistos.append(fn.name)
                assert "apuntar" in llamadas, f"{path.name}:{fn.name} manda el aviso y no lo apunta"
    assert sorted(vistos) == ["_avisar", "_send_suspicious_review", "avisar_han_mudo"], vistos


def test_quien_decide_con_el_boton_olvida_ese_aviso():
    fn = next(f for f in _funciones(SRC / "admin.py") if f.name == "on_suspicious_review_callback")
    assert "olvidar_revision" in _llamadas(fn)
