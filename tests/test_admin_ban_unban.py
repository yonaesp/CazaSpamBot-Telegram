"""Tests integration de cmd_ban / cmd_unban / _resolve_target_user."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db import DB
from src import admin as admin_mod


@pytest.fixture
def db(tmp_path):
    return DB(str(tmp_path / "test.db"))


def _mock_update(text="/ban 12345", chat_type="supergroup", reply_to=None,
                 from_user_id=111111111, chat_id=-1001234567890):
    msg = SimpleNamespace(
        message_id=999,
        text=text,
        reply_to_message=reply_to,
        chat=SimpleNamespace(id=chat_id, type=chat_type),
        chat_id=chat_id,
        delete=AsyncMock(),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_message=msg,
        effective_chat=msg.chat,
        effective_user=SimpleNamespace(id=from_user_id, username="el admin", is_bot=False),
    )
    return update


def _mock_context(db, args=("12345",), admin_user_id=111111111):
    cfg = SimpleNamespace(
        admin_user_id=admin_user_id, shadow=False, federation_enabled=True,
        public_quip_enabled=True, public_quip_delete_after_s=3600, mode="active",
    )
    bot = MagicMock()
    bot.id = 222222222
    bot.get_chat_member = AsyncMock(side_effect=Exception("not found"))
    bot.get_chat = AsyncMock()
    context = SimpleNamespace(
        args=list(args),
        bot=bot,
        bot_data={"cfg": cfg, "db": db, "notifier": MagicMock(send_text=AsyncMock())},
        application=MagicMock(job_queue=None),
    )
    return context


@pytest.mark.asyncio
async def test_resolve_target_numeric():
    update = _mock_update(text="/ban 12345")
    db_mock = MagicMock()
    db_mock.remember_username = MagicMock()
    context = SimpleNamespace(args=["12345"], bot=MagicMock())
    uid, rest, err = await admin_mod._resolve_target_user(update, context, db_mock)
    assert uid == 12345
    assert err is None


@pytest.mark.asyncio
async def test_resolve_target_at_username_from_cache(db):
    db.remember_username("rx10e", 6709150347)
    update = _mock_update(text="/ban @rx10e error")
    context = SimpleNamespace(args=["@rx10e", "error"], bot=MagicMock())
    uid, rest, err = await admin_mod._resolve_target_user(update, context, db)
    assert uid == 6709150347
    assert rest == ["error"]
    assert err is None


@pytest.mark.asyncio
async def test_resolve_target_unknown_username(db):
    from telegram.error import TelegramError
    update = _mock_update(text="/ban @noexist")
    bot = MagicMock()
    bot.get_chat = AsyncMock(side_effect=TelegramError("chat not found"))
    # bot_data sin reporter → el fallback Telethon se salta, devuelve error
    context = SimpleNamespace(args=["@noexist"], bot=bot, bot_data={})
    uid, rest, err = await admin_mod._resolve_target_user(update, context, db)
    assert uid is None
    assert err and "noexist" in err.lower()


@pytest.mark.asyncio
async def test_resolve_target_from_reply():
    reply_user = SimpleNamespace(id=555, username="someone", first_name="Some")
    reply_msg = SimpleNamespace(message_id=998, from_user=reply_user)
    update = _mock_update(text="/ban", reply_to=reply_msg)
    db_mock = MagicMock()
    db_mock.remember_username = MagicMock()
    context = SimpleNamespace(args=[], bot=MagicMock())
    uid, _, err = await admin_mod._resolve_target_user(update, context, db_mock)
    assert uid == 555
    assert err is None
    db_mock.remember_username.assert_called_once_with("someone", 555)


@pytest.mark.asyncio
async def test_resolve_target_no_args_no_reply():
    update = _mock_update(text="/ban")
    db_mock = MagicMock()
    context = SimpleNamespace(args=[], bot=MagicMock())
    uid, _, err = await admin_mod._resolve_target_user(update, context, db_mock)
    assert uid is None


@pytest.mark.asyncio
async def test_resolve_target_negative_id():
    update = _mock_update(text="/ban -100")
    context = SimpleNamespace(args=["-100"], bot=MagicMock())
    uid, _, _ = await admin_mod._resolve_target_user(update, context, MagicMock())
    assert uid == -100


@pytest.mark.asyncio
async def test_resolve_target_text_mention_sin_username():
    """Usuario SIN username mencionado con @nombre → Telegram incrusta
    text_mention con el objeto User. Debe resolverse por su id."""
    mentioned = SimpleNamespace(id=55501, username=None, first_name="SinUser")
    entity = SimpleNamespace(type="text_mention", user=mentioned)
    msg = SimpleNamespace(
        message_id=1, text="/ban SinUser spam", reply_to_message=None,
        chat=SimpleNamespace(id=-100, type="supergroup"), chat_id=-100,
        entities=[entity], delete=AsyncMock(), reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_message=msg, effective_chat=msg.chat,
        effective_user=SimpleNamespace(id=111111111, username="el admin", is_bot=False),
    )
    db_mock = MagicMock()
    db_mock.remember_username = MagicMock()
    context = SimpleNamespace(args=["SinUser", "spam"], bot=MagicMock(), bot_data={})
    uid, rest, err = await admin_mod._resolve_target_user(update, context, db_mock)
    assert uid == 55501
    assert err is None
    assert rest == ["spam"]
