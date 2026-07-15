"""Tests de los botones del aviso de revisión de sospechosos: Permitir/Banear +
toggles de verificación humana y de los propios avisos (editan la notificación)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import admin
from src import verification as v

CHAT = -100500
USER = 42
ADMIN = 999


def test_build_review_keyboard_botones_y_estado(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)  # default: verif=0, review=1
    kb = v.build_review_keyboard(tmp_db, CHAT, USER)
    flat = [b for row in kb.inline_keyboard for b in row]
    cbs = {b.callback_data for b in flat}
    assert f"susrev:allow:{CHAT}:{USER}" in cbs
    assert f"susrev:ban:{CHAT}:{USER}" in cbs
    assert f"susrev:togverif:{CHAT}:{USER}" in cbs
    assert f"susrev:togreview:{CHAT}:{USER}" in cbs
    verif = next(b for b in flat if "Verificación" in b.text)
    assert "OFF" in verif.text            # verificación por defecto OFF
    review = next(b for b in flat if "Avisos" in b.text)
    assert "ON" in review.text            # avisos de revisión por defecto ON


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
async def test_togverif_activa_verificacion(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)
    assert tmp_db.get_chat_settings(CHAT)["verification_enabled"] == 0
    update, context, q = _cbctx(tmp_db, f"susrev:togverif:{CHAT}:{USER}")
    await admin.on_suspicious_review_callback(update, context)
    assert tmp_db.get_chat_settings(CHAT)["verification_enabled"] == 1
    q.edit_message_reply_markup.assert_awaited_once()   # edita la propia notificación


@pytest.mark.asyncio
async def test_togreview_desactiva_avisos(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)
    assert tmp_db.get_chat_settings(CHAT)["verification_review_suspicious"] == 1
    update, context, q = _cbctx(tmp_db, f"susrev:togreview:{CHAT}:{USER}")
    await admin.on_suspicious_review_callback(update, context)
    assert tmp_db.get_chat_settings(CHAT)["verification_review_suspicious"] == 0


@pytest.mark.asyncio
async def test_toggle_solo_admin(tmp_db):
    tmp_db.ensure_chat_settings(CHAT)
    update, context, q = _cbctx(tmp_db, f"susrev:togverif:{CHAT}:{USER}", uid=12345)
    await admin.on_suspicious_review_callback(update, context)
    assert tmp_db.get_chat_settings(CHAT)["verification_enabled"] == 0  # sin cambios
