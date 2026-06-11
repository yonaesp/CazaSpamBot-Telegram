"""Tests de consolidación de bans en ráfaga (ban_announce)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import ban_announce


def _mk_context():
    """Context falso con bot que cuenta sends/deletes."""
    sent_ids = []
    deleted_ids = []

    async def _send(chat_id, text, **kw):
        mid = 1000 + len(sent_ids)
        sent_ids.append((mid, text))
        return SimpleNamespace(message_id=mid)

    async def _delete(chat_id, message_id):
        deleted_ids.append(message_id)

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=_send),
                          delete_message=AsyncMock(side_effect=_delete))
    jq = MagicMock()
    jq.get_jobs_by_name = MagicMock(return_value=[])
    jq.run_once = MagicMock()
    app = SimpleNamespace(job_queue=jq)
    ctx = SimpleNamespace(bot=bot, bot_data={}, application=app)
    return ctx, sent_ids, deleted_ids


@pytest.mark.asyncio
async def test_primeros_dos_son_individuales():
    ctx, sent, deleted = _mk_context()
    await ban_announce.announce_ban(ctx, chat_id=-100, quip_text="ban A", delete_after=3600)
    await ban_announce.announce_ban(ctx, chat_id=-100, quip_text="ban B", delete_after=3600)
    # 2 mensajes individuales, ninguno borrado
    assert len(sent) == 2
    assert deleted == []


@pytest.mark.asyncio
async def test_tercer_ban_consolida():
    ctx, sent, deleted = _mk_context()
    for t in ["ban A", "ban B", "ban C"]:
        await ban_announce.announce_ban(ctx, chat_id=-100, quip_text=t, delete_after=3600)
    # Al 3º: borra los 2 individuales + publica 1 consolidado
    # sent: A(1000), B(1001), consolidado(1002)
    assert len(sent) == 3
    assert 1000 in deleted and 1001 in deleted  # los individuales borrados
    consolidado = sent[2][1]
    assert "3 baneados" in consolidado
    assert "ban A" in consolidado and "ban B" in consolidado and "ban C" in consolidado


@pytest.mark.asyncio
async def test_cuarto_ban_actualiza_consolidado():
    ctx, sent, deleted = _mk_context()
    for t in ["A", "B", "C", "D"]:
        await ban_announce.announce_ban(ctx, chat_id=-100, quip_text=t, delete_after=3600)
    # 4º: borra el consolidado anterior (1002) y publica uno nuevo con 4
    ultimo = sent[-1][1]
    assert "4 baneados" in ultimo
    assert all(x in ultimo for x in ["A", "B", "C", "D"])
    assert 1002 in deleted  # el consolidado anterior borrado


@pytest.mark.asyncio
async def test_chats_distintos_no_se_mezclan():
    ctx, sent, deleted = _mk_context()
    await ban_announce.announce_ban(ctx, chat_id=-100, quip_text="A", delete_after=3600)
    await ban_announce.announce_ban(ctx, chat_id=-200, quip_text="B", delete_after=3600)
    # Cada chat con su propia ráfaga, ambos individuales
    assert len(sent) == 2
    assert deleted == []
