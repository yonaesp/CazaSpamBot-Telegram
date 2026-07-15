"""Tests de los botones del aviso de revisión de sospechosos: vista colapsada
(Permitir/Banear + ⚙️), panel de ajustes (toggles + recordatorios + tiempos) y submenú
de tiempos. Todo edita la propia notificación y respeta el sync."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import admin
from src import verification as v

CHAT = -100500
USER = 42
ADMIN = 999


# --------------------------- teclados ---------------------------

def test_keyboard_colapsado_permitir_banear_tuerca(tmp_db):
    kb = v.build_review_keyboard(tmp_db, CHAT, USER)
    cbs = {b.callback_data for row in kb.inline_keyboard for b in row}
    assert f"susrev:allow:{CHAT}:{USER}" in cbs
    assert f"susrev:ban:{CHAT}:{USER}" in cbs
    assert f"susrev:gear:{CHAT}:{USER}" in cbs
    assert not any("tog" in c for c in cbs)   # colapsado: sin toggles a la vista


def test_panel_ajustes_toggles_y_tiempos(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)  # verif=0, review=1, reminders=1 (default)
    kb = v.build_review_settings_keyboard(tmp_db, CHAT, USER)
    cbs = {b.callback_data for row in kb.inline_keyboard for b in row}
    for a in ("togverif", "togreview", "togremind", "times", "collapse"):
        assert f"susrev:{a}:{CHAT}:{USER}" in cbs, a


def test_panel_sin_tiempos_si_recordatorios_off(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)
    tmp_db.update_chat_setting(CHAT, "verification_reminders_enabled", 0)
    kb = v.build_review_settings_keyboard(tmp_db, CHAT, USER)
    cbs = {b.callback_data for row in kb.inline_keyboard for b in row}
    assert not any("susrev:times" in c for c in cbs)  # sin recordatorios → sin tiempos


def test_submenu_tiempos_presets(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)
    kb = v.build_review_times_keyboard(tmp_db, CHAT, USER)
    cbs = {b.callback_data for row in kb.inline_keyboard for b in row}
    assert f"susrev:st:sk:30:{CHAT}:{USER}" in cbs
    assert f"susrev:gear:{CHAT}:{USER}" in cbs   # volver


# --------------------------- callbacks ---------------------------

def _cbctx(tmp_db, data, uid=ADMIN):
    cfg = SimpleNamespace(admin_user_id=ADMIN, shadow=False)
    q = SimpleNamespace(
        data=data, from_user=SimpleNamespace(id=uid),
        answer=AsyncMock(), edit_message_reply_markup=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(text_html="🔍 aviso"),
    )
    update = SimpleNamespace(callback_query=q)
    context = SimpleNamespace(bot_data={"cfg": cfg, "db": tmp_db}, bot=SimpleNamespace())
    return update, context, q


@pytest.mark.asyncio
async def test_gear_abre_panel(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)
    update, context, q = _cbctx(tmp_db, f"susrev:gear:{CHAT}:{USER}")
    await admin.on_suspicious_review_callback(update, context)
    q.edit_message_reply_markup.assert_awaited_once()
    kb = q.edit_message_reply_markup.await_args.kwargs["reply_markup"]
    cbs = {b.callback_data for row in kb.inline_keyboard for b in row}
    assert f"susrev:togverif:{CHAT}:{USER}" in cbs


@pytest.mark.asyncio
async def test_togverif_activa_verificacion(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)
    update, context, q = _cbctx(tmp_db, f"susrev:togverif:{CHAT}:{USER}")
    await admin.on_suspicious_review_callback(update, context)
    assert tmp_db.get_chat_settings(CHAT)["verification_enabled"] == 1


@pytest.mark.asyncio
async def test_togremind_desactiva_recordatorios(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)
    assert tmp_db.get_chat_settings(CHAT)["verification_reminders_enabled"] == 1
    update, context, q = _cbctx(tmp_db, f"susrev:togremind:{CHAT}:{USER}")
    await admin.on_suspicious_review_callback(update, context)
    assert tmp_db.get_chat_settings(CHAT)["verification_reminders_enabled"] == 0


@pytest.mark.asyncio
async def test_st_fija_tiempo(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)
    update, context, q = _cbctx(tmp_db, f"susrev:st:sk:60:{CHAT}:{USER}")
    await admin.on_suspicious_review_callback(update, context)
    assert tmp_db.get_chat_settings(CHAT)["verification_suspicious_kick_minutes"] == 60
    q.edit_message_reply_markup.assert_awaited_once()


@pytest.mark.asyncio
async def test_st_valor_fuera_de_preset_rechazado(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)
    update, context, q = _cbctx(tmp_db, f"susrev:st:sk:99:{CHAT}:{USER}")
    await admin.on_suspicious_review_callback(update, context)
    assert tmp_db.get_chat_settings(CHAT)["verification_suspicious_kick_minutes"] == 30  # sin cambio


@pytest.mark.asyncio
async def test_toggle_solo_admin(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)
    update, context, q = _cbctx(tmp_db, f"susrev:togverif:{CHAT}:{USER}", uid=12345)
    await admin.on_suspicious_review_callback(update, context)
    assert tmp_db.get_chat_settings(CHAT)["verification_enabled"] == 0  # sin cambios
