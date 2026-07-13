"""Regresión BUG audit 2026-07-10: un usuario legítimo quedaba MUTEADO para
siempre cuando la verificación estaba desactivada en el chat o en modo shadow
(on_chat_member aplicaba mute provisional y on_join retornaba sin desmutear).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import verification as v


def _ctx(shadow: bool, verification_enabled):
    cfg = SimpleNamespace(shadow=shadow, admin_user_id=999)
    db = MagicMock()
    db.get_chat_settings.return_value = {
        "verification_enabled": verification_enabled,
        "verification_review_suspicious": 0,
    }
    bot = SimpleNamespace(restrict_chat_member=AsyncMock())
    return SimpleNamespace(bot=bot, bot_data={"cfg": cfg, "db": db})


@pytest.mark.asyncio
async def test_on_join_desmutea_si_verificacion_desactivada():
    """Verificación OFF en el chat → debe DESMUTEAR (deshacer el mute provisional)."""
    ctx = _ctx(shadow=False, verification_enabled=0)
    chat = SimpleNamespace(id=-100123, title="G")
    user = SimpleNamespace(id=42, username="u", first_name="U", last_name=None)
    await v.on_join(update=None, context=ctx, chat=chat, user=user)
    ctx.bot.restrict_chat_member.assert_awaited_once()
    kwargs = ctx.bot.restrict_chat_member.await_args.kwargs
    assert kwargs["permissions"] is v.VERIFIED_PERMISSIONS  # permisos completos
    assert kwargs["chat_id"] == -100123 and kwargs["user_id"] == 42


@pytest.mark.asyncio
async def test_on_join_en_shadow_no_toca_permisos():
    """En shadow, on_join no ejecuta acciones (y on_chat_member ya no mutea)."""
    ctx = _ctx(shadow=True, verification_enabled=1)
    chat = SimpleNamespace(id=-100, title="G")
    user = SimpleNamespace(id=1, username=None, first_name="X", last_name=None)
    await v.on_join(update=None, context=ctx, chat=chat, user=user)
    ctx.bot.restrict_chat_member.assert_not_awaited()
