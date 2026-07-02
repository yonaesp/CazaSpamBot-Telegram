"""Tests del combo /spam: ban federado + reporte + muestra al clasificador."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db import DB
from src import admin as admin_mod


@pytest.fixture
def db(tmp_path):
    return DB(str(tmp_path / "test.db"))


def _reply(text="compra criptos gratis aquí t.me/+abc", from_user=None, message_id=998):
    if from_user is None:
        from_user = SimpleNamespace(id=555, username="spammer", first_name="Spam", is_bot=False)
    return SimpleNamespace(
        message_id=message_id, text=text, caption=None, from_user=from_user,
    )


def _update(reply_to, chat_id=-1001234567890, admin_id=111111111):
    msg = SimpleNamespace(
        message_id=999, text="/spam", reply_to_message=reply_to,
        chat=SimpleNamespace(id=chat_id, type="supergroup", title="Win11"),
        chat_id=chat_id, delete=AsyncMock(), reply_text=AsyncMock(),
    )
    return SimpleNamespace(
        effective_message=msg, effective_chat=msg.chat,
        effective_user=SimpleNamespace(id=admin_id, username="el admin", is_bot=False),
    )


def _context(db, *, member_status="member", quip=False):
    cfg = SimpleNamespace(
        admin_user_id=111111111, shadow=False, federation_enabled=True,
        public_quip_enabled=quip, public_quip_delete_after_s=3600, mode="active",
    )
    bot = MagicMock()
    bot.id = 222222222
    bot.delete_message = AsyncMock()
    bot.get_chat_member = AsyncMock(
        return_value=SimpleNamespace(status=member_status, user=None)
    )
    reporter = MagicMock()
    reporter.is_ready = MagicMock(return_value=True)
    reporter.reporting_ready = MagicMock(return_value=True)
    reporter.enqueue = MagicMock()
    return SimpleNamespace(
        args=[], bot=bot,
        bot_data={"cfg": cfg, "db": db, "reporter": reporter,
                  "notifier": MagicMock(send_text=AsyncMock())},
        application=MagicMock(job_queue=None),
    )


@pytest.mark.asyncio
async def test_spam_combo_bans_reports_and_learns(db):
    update = _update(_reply())
    ctx = _context(db)
    with patch.object(admin_mod, "federate_ban", new=AsyncMock(return_value={-1001234567890: "ok"})) as fb, \
         patch.object(admin_mod, "_notify_admin_ack", new=AsyncMock()):
        await admin_mod._spam_combo(update, ctx)

    # ban federado al AUTOR del mensaje, no al admin
    fb.assert_awaited_once()
    assert fb.await_args.kwargs["user_id"] == 555
    assert fb.await_args.kwargs["rule"] == "manual_admin_ban"
    # reporte encolado con el message_id del spam
    ctx.bot_data["reporter"].enqueue.assert_called_once()
    assert ctx.bot_data["reporter"].enqueue.call_args.kwargs["message_id"] == 998
    # mensaje del spammer borrado
    ctx.bot.delete_message.assert_awaited_once()
    # muestra spam persistida
    assert db.sample_count()["spam"] == 1


@pytest.mark.asyncio
async def test_spam_no_reply_shows_usage(db):
    update = _update(None)
    ctx = _context(db)
    with patch.object(admin_mod, "federate_ban", new=AsyncMock()) as fb:
        await admin_mod._spam_combo(update, ctx)
    fb.assert_not_awaited()
    update.effective_message.reply_text.assert_awaited_once()
    assert db.sample_count()["spam"] == 0


@pytest.mark.asyncio
async def test_spam_skips_admin_author(db):
    # Sembrar un chat federado donde el bot es admin → guard consulta status
    db.upsert_bot_chat(
        chat_id=-1001234567890, title="Win11", chat_type="supergroup",
        am_admin=True, can_restrict=True, can_delete=True,
    )
    update = _update(_reply())
    ctx = _context(db, member_status="administrator")
    with patch.object(admin_mod, "federate_ban", new=AsyncMock()) as fb, \
         patch.object(admin_mod, "_notify_admin_ack", new=AsyncMock()):
        await admin_mod._spam_combo(update, ctx)
    # No banea a un admin
    fb.assert_not_awaited()
    ctx.bot_data["reporter"].enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_spam_anonymous_author_only_learns(db):
    update = _update(_reply(from_user=None))
    # forward anónimo: from_user None
    update.effective_message.reply_to_message.from_user = None
    ctx = _context(db)
    with patch.object(admin_mod, "federate_ban", new=AsyncMock()) as fb, \
         patch.object(admin_mod, "_notify_admin_ack", new=AsyncMock()):
        await admin_mod._spam_combo(update, ctx)
    fb.assert_not_awaited()
    # pero sí aprende del texto
    assert db.sample_count()["spam"] == 1
