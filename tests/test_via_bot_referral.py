"""Anuncio con enlace de referido publicado con un bot inline (`via_bot_referral`).

Caso real (21-oct-2026, Windows 11): «Lil Pani» (5414865354), miembro desde 2025
con 27 preguntas sobre Windows, publicó con @case_rush_bot «A free case every day
in Case Rush! Stars, gifts and NFTs» con un botón a
`t.me/case_rush_bot/app?startapp=r_5414865354`, su propio código. El bot lo borró
y avisó con «no le he baneado», sin enseñar qué era. Ahora: referido → ban; otros
botones vía bot (encuestas, juegos) → solo borrar, pero con copia al admin.
"""
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import autoaprendizaje, handlers, quips, rule_explain
from src.detectors import inline_buttons as det

UID = 5414865354
CASE_RUSH = f"https://t.me/case_rush_bot/app?startapp=r_{UID}"


def _btn(text, url=None, callback_data=None):
    return NS(text=text, url=url, callback_data=callback_data)


def _msg(*botones, texto="🎁 A free case every day in Case Rush!"):
    return NS(
        text=None, caption=texto, chat_id=-1001190184646, message_id=61553,
        chat=NS(title="Windows 11", id=-1001190184646),
        reply_markup=NS(inline_keyboard=[list(botones)]),
        via_bot=NS(username="case_rush_bot"),
    )


def _user(uid=UID):
    return NS(id=uid, username="Morocho1312", first_name="Lil Pani")


# --- Qué es un enlace de referido ----------------------------------------------

def test_el_caso_real_es_referido():
    assert det.enlaces_de_referido(_msg(_btn("🎁 Open a free case", url=CASE_RUSH)), UID) == [CASE_RUSH]


@pytest.mark.parametrize("url", [
    "https://t.me/algun_bot?start=ref_ABC123",
    "https://t.me/algun_bot?start=ref123",
    "t.me/juego_bot/play?startapp=invite-xyz",
    "tg://resolve?domain=algun_bot&start=r_99",
    f"https://t.me/algun_bot?start={UID}",
    f"https://telegram.me/algun_bot?startapp=u{UID}x",
])
def test_formas_de_referido(url):
    assert det.enlaces_de_referido(_msg(_btn("Jugar", url=url)), UID) == [url]


@pytest.mark.parametrize("url", [
    "https://t.me/send?start=CQaBcD123",           # cheque de cripto: no es referido
    "https://t.me/algun_bot?start=help",
    "https://t.me/algun_bot?start=reference",       # «ref» sin separador ni cifra
    "https://t.me/algun_bot?start=rabbit",
    "https://t.me/canal_de_noticias/123",
    "https://example.com/?start=ref_1",             # no es Telegram
])
def test_no_es_referido(url):
    assert det.enlaces_de_referido(_msg(_btn("Ver", url=url)), UID) == []


def test_botones_de_callback_no_son_referido():
    """Una encuesta de @vote o un juego llevan callbacks, no enlaces."""
    assert det.enlaces_de_referido(_msg(_btn("👍 12", callback_data="v:1")), UID) == []


# --- El manejador ------------------------------------------------------------

def _ctx():
    ctx = MagicMock()
    ctx.bot.copy_message = AsyncMock()
    ctx.bot.delete_message = AsyncMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def _db(whitelisted=False):
    db = MagicMock()
    db.is_whitelisted.return_value = whitelisted
    return db


_CFG = NS(admin_user_id=111, admin_notify_chat_id=111, shadow=False)


@pytest.mark.asyncio
async def test_referido_va_a_ban(monkeypatch):
    aplicar = AsyncMock()
    monkeypatch.setattr(handlers, "_apply_action", aplicar)
    ctx = _ctx()
    hecho = await handlers._moderate_via_bot_message(
        ctx, _db(), _CFG, _msg(_btn("🎁 Open a free case", url=CASE_RUSH)), _user())
    assert hecho is True
    decision = aplicar.await_args.kwargs["decision"]
    assert (decision.action, decision.rule) == ("ban", "via_bot_referral")
    assert decision.score >= 100
    assert decision.payload["urls"] == [CASE_RUSH]
    # El borrado y la copia al admin los hace `_apply_action`, no este camino.
    ctx.bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_sin_referido_solo_borra_pero_copia_antes(monkeypatch):
    aplicar = AsyncMock()
    monkeypatch.setattr(handlers, "_apply_action", aplicar)
    orden = []
    ctx = _ctx()
    ctx.bot.copy_message.side_effect = lambda **kw: orden.append("copia")
    ctx.bot.delete_message.side_effect = lambda **kw: orden.append("borrado")
    url = "https://t.me/canal_de_noticias/123"
    hecho = await handlers._moderate_via_bot_message(
        ctx, _db(), _CFG, _msg(_btn("Leer", url=url)), _user())
    assert hecho is True
    aplicar.assert_not_awaited()
    assert orden == ["copia", "borrado"]
    aviso = ctx.bot.send_message.await_args.kwargs["text"]
    assert url in aviso and "{botones}" not in aviso


@pytest.mark.parametrize("uid,whitelisted", [(111, False), (UID, True)])
@pytest.mark.asyncio
async def test_dueno_y_lista_blanca_no_se_tocan(monkeypatch, uid, whitelisted):
    aplicar = AsyncMock()
    monkeypatch.setattr(handlers, "_apply_action", aplicar)
    ctx = _ctx()
    hecho = await handlers._moderate_via_bot_message(
        ctx, _db(whitelisted), _CFG, _msg(_btn("Jugar", url=CASE_RUSH)), _user(uid))
    assert hecho is False
    aplicar.assert_not_awaited()
    ctx.bot.delete_message.assert_not_awaited()


def test_regla_registrada():
    assert "via_bot_referral" in rule_explain.KNOWN_RULES
    assert "via_bot_referral" in quips._RULES
    assert "via_bot_referral" in handlers.HARD_RULES_BAN
    assert "via_bot_referral" in autoaprendizaje._REGLAS_DE_CONTENIDO
    # Score 100 < 150: un miembro real no se reporta a Telegram por esto.
    assert "via_bot_referral" not in handlers._REPORTABLE_RULES
    assert "referido" in rule_explain.explain("via_bot_referral").lower()
