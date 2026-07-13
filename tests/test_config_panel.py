"""Tests del panel de ajustes por botones (/config)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import config_panel as cp
from telegram import InlineKeyboardMarkup

ADMIN = 999
CID = -100123


def _settings(**over):
    base = {
        "verification_enabled": 1,
        "verification_review_suspicious": 0,
        "verification_reminders_enabled": 1,
        "verification_kick_normal": 1,
        "verification_suspicious_kick_minutes": 30,
        "verification_reminder_hours": 3,
        "verification_kick_after_reminder_hours": 6,
        "welcome_enabled": 1,
        "cleanservice": 1,
    }
    base.update(over)
    return base


def _db(settings=None, chats=None):
    db = MagicMock()
    db.get_chat_settings.return_value = settings if settings is not None else _settings()
    db.all_chats.return_value = chats if chats is not None else [
        {"chat_id": CID, "title": "Grupo Test", "am_admin": True},
    ]
    return db


def _cbctx(db, user_id=ADMIN):
    cfg = SimpleNamespace(admin_user_id=ADMIN)
    q = SimpleNamespace(
        data=None,
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        message=SimpleNamespace(chat_id=ADMIN),
    )
    update = SimpleNamespace(callback_query=q)
    context = SimpleNamespace(
        bot_data={"cfg": cfg, "db": db},
        user_data={},
        bot=SimpleNamespace(send_message=AsyncMock()),
    )
    return update, context, q


# ------------------------------- teclados -------------------------------

def test_panel_keyboard_estado_en_etiquetas():
    kb = cp.build_panel_keyboard(CID, _settings(verification_enabled=0, welcome_enabled=1))
    flat = [b for row in kb.inline_keyboard for b in row]
    verif = next(b for b in flat if "Verificación" in b.text)
    assert "❌ OFF" in verif.text
    assert verif.callback_data == f"cfg:tog:verification_enabled:{CID}"
    welcome = next(b for b in flat if b.text.startswith("👋"))
    assert "✅ ON" in welcome.text


def test_panel_keyboard_accion_refleja_kick_mute():
    kb_kick = cp.build_panel_keyboard(CID, _settings(verification_kick_normal=1))
    kb_mute = cp.build_panel_keyboard(CID, _settings(verification_kick_normal=0))
    txt_kick = [b.text for row in kb_kick.inline_keyboard for b in row]
    txt_mute = [b.text for row in kb_mute.inline_keyboard for b in row]
    assert any("Expulsar" in t for t in txt_kick)
    assert any("Silenciar" in t for t in txt_mute)


def test_times_keyboard_marca_actual():
    kb = cp.build_times_keyboard(CID, _settings(verification_suspicious_kick_minutes=60))
    flat = [b for row in kb.inline_keyboard for b in row]
    sel = next(b for b in flat if b.callback_data == f"cfg:st:sk:60:{CID}")
    assert sel.text.startswith("✅")


# ------------------------------- callbacks -------------------------------

@pytest.mark.asyncio
async def test_toggle_invierte_campo():
    db = _db(_settings(cleanservice=1))
    update, context, q = _cbctx(db)
    q.data = f"cfg:tog:cleanservice:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "cleanservice", 0)
    q.edit_message_reply_markup.assert_awaited_once()


@pytest.mark.asyncio
async def test_accion_invierte_kick_normal():
    db = _db(_settings(verification_kick_normal=1))
    update, context, q = _cbctx(db)
    q.data = f"cfg:accion:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "verification_kick_normal", 0)


@pytest.mark.asyncio
async def test_set_tiempo_valido():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:st:rh:6:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "verification_reminder_hours", 6)


@pytest.mark.asyncio
async def test_set_tiempo_fuera_de_preset_rechazado():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:st:rh:99:{CID}"  # 99 no está en los presets
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()


@pytest.mark.asyncio
async def test_toggle_campo_no_permitido_rechazado():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:tog:warns_limit:{CID}"  # no está en _TOGGLE_FIELDS
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()


@pytest.mark.asyncio
async def test_guard_solo_admin():
    db = _db()
    update, context, q = _cbctx(db, user_id=12345)  # no admin
    q.data = f"cfg:tog:cleanservice:{CID}"
    await cp.on_callback(update, context)
    q.answer.assert_awaited_once()
    assert q.answer.await_args.kwargs.get("show_alert") is True
    db.update_chat_setting.assert_not_called()


@pytest.mark.asyncio
async def test_edit_arma_estado_de_captura():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:edit:w:{CID}"
    await cp.on_callback(update, context)
    assert context.user_data["cfg_await"] == {"chat_id": CID, "field": "welcome_text"}
    q.edit_message_text.assert_awaited_once()


# ------------------------------- captura -------------------------------

@pytest.mark.asyncio
async def test_capture_sin_pendiente_devuelve_false():
    db = _db()
    context = SimpleNamespace(bot_data={"db": db}, user_data={})
    update = SimpleNamespace(effective_message=SimpleNamespace(text="hola", caption=None,
                                                               reply_text=AsyncMock()))
    assert await cp.handle_capture(update, context) is False


@pytest.mark.asyncio
async def test_capture_welcome_guarda_y_parsea_botones():
    db = _db()
    context = SimpleNamespace(bot_data={"db": db},
                              user_data={"cfg_await": {"chat_id": CID, "field": "welcome_text"}})
    msg = SimpleNamespace(
        text="Hola {name} [Reglas](buttonurl://https://t.me/x)",
        caption=None, reply_text=AsyncMock(),
    )
    update = SimpleNamespace(effective_message=msg)
    consumed = await cp.handle_capture(update, context)
    assert consumed is True
    # texto guardado sin el botón Rose
    call = db.update_chat_setting.call_args
    assert call.args[0] == CID and call.args[1] == "welcome_text"
    assert "buttonurl" not in call.args[2] and "Hola {name}" in call.args[2]
    db.add_welcome_button.assert_called_once()
    assert "cfg_await" not in context.user_data  # un solo uso
    msg.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_capture_rules_guarda_texto_plano():
    db = _db()
    context = SimpleNamespace(bot_data={"db": db},
                              user_data={"cfg_await": {"chat_id": CID, "field": "rules_text"}})
    msg = SimpleNamespace(text="No spam.", caption=None, reply_text=AsyncMock())
    update = SimpleNamespace(effective_message=msg)
    assert await cp.handle_capture(update, context) is True
    db.update_chat_setting.assert_called_once_with(CID, "rules_text", "No spam.")


# ------------------------------- comando -------------------------------

@pytest.mark.asyncio
async def test_cmd_config_dm_un_grupo_abre_panel():
    db = _db()
    cfg = SimpleNamespace(admin_user_id=ADMIN)
    context = SimpleNamespace(bot_data={"cfg": cfg, "db": db}, user_data={})
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=ADMIN),
        effective_chat=SimpleNamespace(id=ADMIN, type="private"),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )
    await cp.cmd_config(update, context)
    kwargs = update.effective_message.reply_text.await_args.kwargs
    assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)


@pytest.mark.asyncio
async def test_cmd_config_dm_varios_grupos_muestra_selector():
    chats = [
        {"chat_id": -1, "title": "A", "am_admin": True},
        {"chat_id": -2, "title": "B", "am_admin": True},
    ]
    db = _db(chats=chats)
    cfg = SimpleNamespace(admin_user_id=ADMIN)
    context = SimpleNamespace(bot_data={"cfg": cfg, "db": db}, user_data={})
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=ADMIN),
        effective_chat=SimpleNamespace(id=ADMIN, type="private"),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )
    await cp.cmd_config(update, context)
    args = update.effective_message.reply_text.await_args
    assert "grupo" in args.args[0].lower()
    kb = args.kwargs["reply_markup"]
    assert len(kb.inline_keyboard) == 2


@pytest.mark.asyncio
async def test_cmd_config_no_admin_no_hace_nada():
    db = _db()
    cfg = SimpleNamespace(admin_user_id=ADMIN)
    context = SimpleNamespace(bot_data={"cfg": cfg, "db": db}, user_data={})
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=555),
        effective_chat=SimpleNamespace(id=ADMIN, type="private"),
        effective_message=SimpleNamespace(reply_text=reply),
    )
    await cp.cmd_config(update, context)
    reply.assert_not_awaited()
