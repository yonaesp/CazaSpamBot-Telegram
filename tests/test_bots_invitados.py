"""Bots invitados: el bot que contesta en un grupo del que no es miembro.

Caso real (5-nov-2026, Domótica/Alexa): una cuenta nueva escribió «@xcb1cv5fdbot
@dsfsfds56bot @cxvxcrfdsfbot» y fue baneada en 1 s, pero dos de esos bots
contestaron a los 3 y a los 9 s con un anuncio en chino y diez botones. La sonda tras
el ban borró el primero (451502) y ya había parado cuando llegó el segundo (451503).
"""
import ast
import inspect
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest

from src import bots_invitados, handlers

LLAMADA = "@xcb1cv5fdbot  @dsfsfds56bot  @cxvxcrfdsfbot"
SPAM = "过机假钞🔥视频看货🔥质量保证日常使用、嫖娼、赌博、酒吧、按摩、ktv都可出货"
CHAT, ADMIN_DM, BANEADO_MSG = -1001156069668, 345, 451501


@pytest.fixture(autouse=True)
def _sin_esperas(monkeypatch):
    async def _nada(_s):
        return None
    monkeypatch.setattr(bots_invitados.asyncio, "sleep", _nada)


def test_mencionados_saca_los_bots_de_la_llamada_real():
    assert bots_invitados.mencionados(LLAMADA) == {"xcb1cv5fdbot", "dsfsfds56bot", "cxvxcrfdsfbot"}


@pytest.mark.parametrize("texto", [
    "hola @juanito, ¿qué tal?", "escribe a soporte@ayudabot.com", "sin menciones", "", None,
])
def test_mencionados_no_saca_personas_ni_correos(texto):
    assert bots_invitados.mencionados(texto) == set()


def test_llamante():
    assert bots_invitados.llamante(NS(guest_bot_caller_user=NS(id=8886885856))) == 8886885856
    assert bots_invitados.llamante(NS(guest_bot_caller_user=None)) is None
    assert bots_invitados.llamante(NS()) is None


def _bot_falso(mensajes: dict, miembros: set[int] = frozenset()):
    """Imita la Bot API: forwardMessage da el autor o «not found»; get_chat_member,
    `left` para quien no está (lo que devuelve con un bot invitado)."""
    bot = MagicMock()
    copias = iter(range(9000, 9100))

    async def forward_message(chat_id, from_chat_id, message_id, disable_notification):
        if message_id not in mensajes:
            raise BadRequest("Message to forward not found")
        autor, texto = mensajes[message_id]
        return NS(message_id=next(copias), forward_origin=NS(sender_user=autor), text=texto, caption=None)

    async def get_chat_member(chat_id, user_id):
        return NS(status="member" if user_id in miembros else "left")

    bot.forward_message = AsyncMock(side_effect=forward_message)
    bot.get_chat_member = AsyncMock(side_effect=get_chat_member)
    bot.delete_message = AsyncMock()
    return bot


BOT_SPAM = NS(id=9266315643, username="cxvxcrfdsfbot", is_bot=True, first_name="wdsfsdg")


@pytest.mark.asyncio
async def test_la_pasada_tardia_retira_el_mensaje_que_se_quedo_seis_horas():
    # 451502 ya lo borró la limpieza normal: ahora da «not found».
    bot = _bot_falso({451503: (BOT_SPAM, SPAM)})
    actuar = AsyncMock()
    n = await bots_invitados.barrer(bot, CHAT, ADMIN_DM, BANEADO_MSG,
                                    bots_invitados.mencionados(LLAMADA), actuar, esperas=(0,))
    assert n == 1
    actuar.assert_awaited_once()
    msg_id, autor, texto = actuar.await_args.args
    assert (msg_id, autor.id, texto) == (451503, BOT_SPAM.id, SPAM)


@pytest.mark.asyncio
async def test_la_copia_del_privado_se_borra_siempre():
    persona = NS(id=1, username="ana", is_bot=False)
    bot = _bot_falso({451502: (persona, "hola"), 451503: (BOT_SPAM, SPAM)})
    await bots_invitados.barrer(bot, CHAT, ADMIN_DM, BANEADO_MSG, {"cxvxcrfdsfbot"},
                                AsyncMock(), esperas=(0,))
    en_privado = [c for c in bot.delete_message.await_args_list if c.kwargs["chat_id"] == ADMIN_DM]
    assert len(en_privado) == 2


@pytest.mark.asyncio
async def test_no_toca_a_una_persona_ni_a_un_bot_no_mencionado():
    persona = NS(id=1, username="cxvxcrfdsfbot_fan", is_bot=False)
    otro_bot = NS(id=2, username="otrobot", is_bot=True)
    bot = _bot_falso({451502: (persona, SPAM), 451503: (otro_bot, SPAM)})
    actuar = AsyncMock()
    assert await bots_invitados.barrer(bot, CHAT, ADMIN_DM, BANEADO_MSG, {"cxvxcrfdsfbot"},
                                       actuar, esperas=(0,)) == 0
    actuar.assert_not_awaited()


@pytest.mark.asyncio
async def test_un_bot_de_la_casa_mencionado_por_el_spammer_no_se_toca():
    """El spammer puede mencionar al bot de warns del grupo: es miembro, no es invitado."""
    rose = NS(id=609517172, username="missrose_bot", is_bot=True)
    bot = _bot_falso({451502: (rose, "warn 1/3")}, miembros={rose.id})
    actuar = AsyncMock()
    assert await bots_invitados.barrer(bot, CHAT, ADMIN_DM, BANEADO_MSG, {"missrose_bot"},
                                       actuar, esperas=(0,)) == 0
    actuar.assert_not_awaited()


@pytest.mark.asyncio
async def test_si_no_se_puede_saber_si_es_miembro_no_se_toca():
    bot = _bot_falso({451503: (BOT_SPAM, SPAM)})
    bot.get_chat_member = AsyncMock(side_effect=BadRequest("Timed out"))
    actuar = AsyncMock()
    assert await bots_invitados.barrer(bot, CHAT, ADMIN_DM, BANEADO_MSG, {"cxvxcrfdsfbot"},
                                       actuar, esperas=(0,)) == 0


@pytest.mark.asyncio
async def test_la_segunda_pasada_no_vuelve_a_sondear_lo_visto():
    persona = NS(id=1, username="ana", is_bot=False)
    mensajes = {451502: (persona, "hola")}
    bot = _bot_falso(mensajes)
    actuar = AsyncMock()

    real = bot.forward_message.side_effect

    async def llega_tarde(**kw):
        # El bot invitado contesta entre la primera y la segunda pasada.
        if bot.forward_message.await_count > 4:
            mensajes[451503] = (BOT_SPAM, SPAM)
        return await real(**kw)

    bot.forward_message.side_effect = llega_tarde
    await bots_invitados.barrer(bot, CHAT, ADMIN_DM, BANEADO_MSG, {"cxvxcrfdsfbot"},
                                actuar, esperas=(0, 0))
    sondeados = [c.kwargs["message_id"] for c in bot.forward_message.await_args_list]
    assert sondeados.count(451502) == 1
    assert [c.args[0] for c in actuar.await_args_list] == [451503]


@pytest.mark.asyncio
async def test_un_fallo_al_actuar_no_se_escapa():
    bot = _bot_falso({451503: (BOT_SPAM, SPAM)})
    actuar = AsyncMock(side_effect=RuntimeError("red"))
    assert await bots_invitados.barrer(bot, CHAT, ADMIN_DM, BANEADO_MSG, {"cxvxcrfdsfbot"},
                                       actuar, esperas=(0,)) == 1


# ------------------------------------------------------------- enganche en handlers

def _ctx():
    ctx = MagicMock()
    ctx.bot.id = 8837782565
    db = MagicMock()
    db.is_banned = MagicMock(return_value=True)
    ctx.bot_data = {"db": db, "cfg": NS(admin_notify_chat_id=ADMIN_DM)}
    ctx.application.create_task = MagicMock()
    return ctx, db


@pytest.mark.asyncio
async def test_tras_un_ban_que_menciona_bots_vuelve_a_pasar(monkeypatch):
    ctx, _ = _ctx()
    monkeypatch.setattr(handlers, "_cleanup_consecutive_after_ban", AsyncMock(return_value=1))
    barrer = AsyncMock(return_value=1)
    monkeypatch.setattr(handlers.bots_invitados, "barrer", barrer)
    await handlers._safe_cleanup_consecutive(ctx, CHAT, 8886885856, BANEADO_MSG, 0.0, banned_text=LLAMADA)
    barrer.assert_awaited_once()
    assert barrer.await_args.args[4] == {"xcb1cv5fdbot", "dsfsfds56bot", "cxvxcrfdsfbot"}


@pytest.mark.asyncio
async def test_sin_bots_mencionados_no_hay_pasada_tardia(monkeypatch):
    ctx, _ = _ctx()
    monkeypatch.setattr(handlers, "_cleanup_consecutive_after_ban", AsyncMock(return_value=0))
    barrer = AsyncMock()
    monkeypatch.setattr(handlers.bots_invitados, "barrer", barrer)
    await handlers._safe_cleanup_consecutive(ctx, CHAT, 1, BANEADO_MSG, 0.0, banned_text="compra aquí")
    barrer.assert_not_awaited()


@pytest.mark.asyncio
async def test_lo_que_encuentra_la_pasada_se_banea_como_bot_invitado(monkeypatch):
    ctx, _ = _ctx()
    monkeypatch.setattr(handlers, "_cleanup_consecutive_after_ban", AsyncMock(return_value=0))
    aplicar = AsyncMock()
    monkeypatch.setattr(handlers, "_apply_action", aplicar)

    async def barrer(bot, chat_id, admin_dm, desde_id, bots, actuar, **kw):
        await actuar(451503, BOT_SPAM, SPAM)
        return 1

    monkeypatch.setattr(handlers.bots_invitados, "barrer", barrer)
    await handlers._safe_cleanup_consecutive(ctx, CHAT, 8886885856, BANEADO_MSG, 0.0, banned_text=LLAMADA)
    kw = aplicar.await_args.kwargs
    assert (kw["user_id"], kw["message_id"]) == (BOT_SPAM.id, 451503)
    assert kw["decision"].rule == "bot_invitado" and kw["decision"].action == "ban"
    assert kw["decision"].payload["llamado_por"] == 8886885856


def _msg_invitado(llamado_por):
    return NS(chat_id=CHAT, chat=NS(title="Alexa"), message_id=451503, text=SPAM, caption=None,
              guest_bot_caller_user=NS(id=llamado_por))


@pytest.mark.asyncio
async def test_si_llega_por_la_bot_api_y_lo_llamo_un_baneado_fuera(monkeypatch):
    ctx, db = _ctx()
    aplicar = AsyncMock()
    monkeypatch.setattr(handlers, "_apply_action", aplicar)
    await handlers._moderate_bot_message(ctx, db, ctx.bot_data["cfg"], _msg_invitado(8886885856), BOT_SPAM)
    kw = aplicar.await_args.kwargs
    assert kw["decision"].rule == "bot_invitado" and kw["message_id"] == 451503
    db.is_banned.assert_called_once_with(8886885856)


@pytest.mark.asyncio
async def test_bot_invitado_por_alguien_no_baneado_sigue_la_ruta_de_siempre(monkeypatch):
    """Llamar a un bot no es spam: si quien lo llama no está baneado, solo cuenta el
    spam real del mensaje, como con cualquier bot (la ruta de bots de L40)."""
    ctx, db = _ctx()
    db.is_banned.return_value = False
    aplicar = AsyncMock()
    monkeypatch.setattr(handlers, "_apply_action", aplicar)
    monkeypatch.setattr(handlers.url_det, "check", lambda *a, **k: handlers.Hit.none())
    monkeypatch.setattr(handlers.comad_det, "check", lambda *a, **k: handlers.Hit.none())
    monkeypatch.setattr(handlers.destinos, "fichados", lambda db: set())
    ctx.bot_data["cfg"].url_blocklist = []
    await handlers._moderate_bot_message(ctx, db, ctx.bot_data["cfg"], _msg_invitado(42), BOT_SPAM)
    aplicar.assert_not_awaited()


def test_apply_action_le_pasa_el_texto_a_la_sonda():
    """Sin el texto del mensaje baneado no se sabe a qué bots llamó."""
    arbol = ast.parse(inspect.getsource(handlers._apply_action).lstrip())
    llamadas = [n for n in ast.walk(arbol) if isinstance(n, ast.Call)
                and getattr(n.func, "id", None) == "_safe_cleanup_consecutive"]
    assert llamadas, "_apply_action ya no lanza la sonda"
    for c in llamadas:
        kws = {k.arg: k.value for k in c.keywords}
        assert getattr(kws.get("banned_text"), "id", None) == "original_text"


def test_bot_invitado_no_es_reportable_ni_tiene_frase_publica():
    """Su ban ya lo explica el del que lo llamó; y no se reporta (regla 9)."""
    from src import quips
    assert "bot_invitado" not in quips._RULES
    assert "bot_invitado" not in handlers._REPORTABLE_RULES
