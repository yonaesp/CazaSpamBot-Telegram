"""Usuario de mucha confianza + algo sospechoso: el bot no actúa, pero avisa.

Antes esto era silencio absoluto: con trust >=70 el bot anulaba la acción y no lo
contaba a nadie. Pero una cuenta de confianza puede estar robada, o su dueño puede
haber compartido algo sin mirarlo. Ahora llega un aviso por privado con tres
botones (nada / avisar / banear) y decide el admin.

Solo por PRIVADO: señalar en el grupo a un veterano por algo que el bot ha decidido
no castigar haría más daño que el propio mensaje.
"""
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import handlers
from src.db import DB


def _cfg(**kw):
    base = dict(admin_user_id=1, admin_notify_chat_id=1, shadow=False,
                notify_bot_removed=True)
    base.update(kw)
    return types.SimpleNamespace(**base)


def _msg():
    m = MagicMock()
    m.text = "mira esto https://t.me/+algo"
    m.caption = None
    m.chat_id = -100100
    m.message_id = 42
    m.chat = types.SimpleNamespace(title="Grupo", id=-100100)
    return m


@pytest.mark.asyncio
async def test_avisa_por_privado_con_los_tres_botones(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    cfg = _cfg()
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot_data = {"cfg": cfg, "db": db}
    user = types.SimpleNamespace(id=777, first_name="Veterano", username="vet")

    await handlers._send_trust_notice(
        ctx, db, cfg, _msg(), user, rules=["story_share"],
        reason="motivo", proposed_action="ban", trust=85,
    )

    assert ctx.bot.send_message.await_count == 1, "no avisó al admin"
    kwargs = ctx.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 1, "el aviso NO puede ir al grupo, solo al privado"
    botones = [b.callback_data for fila in kwargs["reply_markup"].inline_keyboard
               for b in fila if b.callback_data]
    acciones = {c.split(":")[1] for c in botones if c.startswith("tnote:")}
    assert acciones == {"nada", "warn", "ban"}, f"faltan botones: {acciones}"


@pytest.mark.asyncio
async def test_los_callbacks_caben_en_los_64_bytes(tmp_path):
    """callback_data tiene un tope duro de 64 bytes: pasarse rompe el botón."""
    db = DB(str(tmp_path / "t.db"))
    cfg = _cfg()
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot_data = {"cfg": cfg, "db": db}
    m = _msg()
    m.chat_id = -1001234567890      # ids reales, largos
    m.message_id = 999999
    user = types.SimpleNamespace(id=9876543210, first_name="X", username=None)

    await handlers._send_trust_notice(ctx, db, cfg, m, user, rules=["story_share"],
                                      reason="r", proposed_action="ban", trust=90)
    kwargs = ctx.bot.send_message.await_args.kwargs
    for fila in kwargs["reply_markup"].inline_keyboard:
        for b in fila:
            if b.callback_data:
                assert len(b.callback_data.encode()) <= 64, b.callback_data


@pytest.mark.asyncio
async def test_se_puede_silenciar(tmp_path):
    """Es un aviso informativo: tiene que poder apagarse desde /alertas."""
    from src import notify_prefs
    db = DB(str(tmp_path / "t.db"))
    cfg = _cfg()
    db.set_pref("notify_trust_skip", False)
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot_data = {"cfg": cfg, "db": db}
    user = types.SimpleNamespace(id=777, first_name="V", username=None)

    assert "trust_skip" in notify_prefs.NOTIFY_TYPES, "no aparece en /alertas"
    await handlers._send_trust_notice(ctx, db, cfg, _msg(), user, rules=["r"],
                                      reason="x", proposed_action="ban", trust=85)
    assert ctx.bot.send_message.await_count == 0, "avisó estando silenciado"
