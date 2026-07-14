"""Tests de moderación de mensajes publicados EN NOMBRE DE UN CANAL (sender_chat)
en grupos de discusión/comentarios: banChatSenderChat ante reglas fuertes, con
guards para no tocar el post auto-reenviado ni a los admins anónimos.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import handlers
from src.detectors import Hit

CID = -1001234567890
SCID = -1009876543210


def _msg(*, auto_forward=False, sc_id=SCID, title="Canal Spam", username="spamch"):
    sc = SimpleNamespace(id=sc_id, title=title, username=username)
    chat = SimpleNamespace(id=CID, title="Grupo Comentarios", type="supergroup")
    return SimpleNamespace(
        sender_chat=sc, is_automatic_forward=auto_forward,
        chat_id=CID, chat=chat, message_id=555,
        text="lo que sea", caption=None,
    )


def _ctx(shadow=False):
    cfg = SimpleNamespace(shadow=shadow, url_blocklist=set(),
                          admin_notify_chat_id=14573395,
                          allowed_scripts=["latin"], non_latin_ratio_threshold=0.30,
                          is_moderated=lambda cid: True)
    db = MagicMock()
    bot = SimpleNamespace(
        ban_chat_sender_chat=AsyncMock(), delete_message=AsyncMock(),
        send_message=AsyncMock(), id=42,
    )
    return SimpleNamespace(bot=bot, bot_data={"cfg": cfg, "db": db}), cfg, db, bot


def _patch_detectors(monkeypatch, spam=False):
    """Aísla los detectores: `spam=True` hace que uno dispare (commercial_ad)."""
    none = SimpleNamespace(check=lambda *a, **k: Hit.none())
    monkeypatch.setattr(handlers, "buttons_det", none)
    monkeypatch.setattr(handlers, "url_det", none)
    monkeypatch.setattr(handlers, "contact_det", none)
    if spam:
        hit = Hit(rule="commercial_ad", score=45, reason="oferta")
        monkeypatch.setattr(handlers, "comad_det", SimpleNamespace(check=lambda *a, **k: hit))
    else:
        monkeypatch.setattr(handlers, "comad_det", none)
    monkeypatch.setattr(handlers, "_ensure_chat_registered", AsyncMock())


@pytest.mark.asyncio
async def test_post_auto_reenviado_se_ignora(monkeypatch):
    """El post del canal que encabeza el hilo (is_automatic_forward) NO se toca."""
    _patch_detectors(monkeypatch, spam=True)  # aunque 'dispararía', ni se evalúa
    ctx, cfg, db, bot = _ctx()
    await handlers._moderate_channel_message(ctx, db, cfg, _msg(auto_forward=True))
    bot.ban_chat_sender_chat.assert_not_awaited()
    db.log_action.assert_not_called()


@pytest.mark.asyncio
async def test_admin_anonimo_se_ignora(monkeypatch):
    """Admin anónimo (sender_chat == el propio grupo) NO se banea."""
    _patch_detectors(monkeypatch, spam=True)
    ctx, cfg, db, bot = _ctx()
    await handlers._moderate_channel_message(ctx, db, cfg, _msg(sc_id=CID))
    bot.ban_chat_sender_chat.assert_not_awaited()
    db.log_action.assert_not_called()


@pytest.mark.asyncio
async def test_canal_benigno_no_se_banea(monkeypatch):
    """Un canal que comenta sin disparar reglas fuertes se deja pasar."""
    _patch_detectors(monkeypatch, spam=False)
    ctx, cfg, db, bot = _ctx()
    await handlers._moderate_channel_message(ctx, db, cfg, _msg())
    bot.ban_chat_sender_chat.assert_not_awaited()
    db.log_action.assert_not_called()


@pytest.mark.asyncio
async def test_canal_spam_se_banea_y_borra(monkeypatch):
    """Regla fuerte → banChatSenderChat + delete + auditoría en modo activo."""
    _patch_detectors(monkeypatch, spam=True)
    ctx, cfg, db, bot = _ctx()
    await handlers._moderate_channel_message(ctx, db, cfg, _msg())
    bot.ban_chat_sender_chat.assert_awaited_once_with(chat_id=CID, sender_chat_id=SCID)
    bot.delete_message.assert_awaited_once()
    db.log_action.assert_called_once()
    kwargs = db.log_action.call_args.kwargs
    assert kwargs["action"] == "ban" and kwargs["mode"] == "active"
    assert kwargs["rule"].startswith("channel_sender+")
    bot.send_message.assert_awaited_once()  # aviso al admin


@pytest.mark.asyncio
async def test_shadow_no_actua_pero_audita(monkeypatch):
    """En shadow no banea ni borra, pero registra la acción con mode=shadow."""
    _patch_detectors(monkeypatch, spam=True)
    ctx, cfg, db, bot = _ctx(shadow=True)
    await handlers._moderate_channel_message(ctx, db, cfg, _msg())
    bot.ban_chat_sender_chat.assert_not_awaited()
    bot.delete_message.assert_not_awaited()
    db.log_action.assert_called_once()
    assert db.log_action.call_args.kwargs["mode"] == "shadow"


@pytest.mark.asyncio
async def test_chat_no_moderado_se_ignora(monkeypatch):
    """Si el chat no está en la lista de moderados, no se actúa."""
    _patch_detectors(monkeypatch, spam=True)
    ctx, cfg, db, bot = _ctx()
    cfg.is_moderated = lambda cid: False
    await handlers._moderate_channel_message(ctx, db, cfg, _msg())
    bot.ban_chat_sender_chat.assert_not_awaited()
    db.log_action.assert_not_called()
