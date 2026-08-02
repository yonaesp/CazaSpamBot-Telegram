"""Qué hace `/ban` respondiendo a un mensaje, y qué se ve en el grupo.

Antes: baneaba, borraba el comando del admin y ya. El mensaje del spammer se
quedaba a la vista y no se publicaba nada, porque el aviso iba atado a los quips
y esos están desactivados por defecto.

Ahora el MOTIVO actúa como consentimiento: sin motivo el ban sigue siendo mudo
(coherente con «baneos silenciosos por defecto»), y si el admin escribe uno es que
quiere que el grupo lo sepa, así que se publica y se queda.
"""
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import admin
from src.db import DB


def _cfg(shadow=False, ttl=0):
    return types.SimpleNamespace(
        admin_user_id=1, admin_notify_chat_id=1, shadow=shadow,
        federation_enabled=True, public_quip_enabled=False,
        public_quip_delete_after_s=3600, ban_notice_delete_after_s=ttl,
        quip_on_auto_ban=False,
    )


def _setup(tmp_path, args, shadow=False, ttl=0):
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(-100100, "G", "supergroup", True, True, True)
    db.ensure_chat_settings(-100100)

    objetivo = MagicMock()
    objetivo.message_id = 4242
    objetivo.from_user = types.SimpleNamespace(id=777, username="spammer",
                                               first_name="Spammer", is_bot=False)
    msg = MagicMock()
    msg.message_id = 99
    msg.chat_id = -100100
    msg.chat = types.SimpleNamespace(id=-100100, type="supergroup", title="G")
    msg.reply_to_message = objetivo
    msg.reply_text = AsyncMock()
    msg.delete = AsyncMock(return_value=True)

    upd = MagicMock()
    upd.effective_message = msg
    upd.effective_chat = types.SimpleNamespace(id=-100100, type="supergroup", title="G")
    upd.effective_user = types.SimpleNamespace(id=1, username="admin", first_name="A")

    ctx = MagicMock()
    ctx.args = args
    ctx.bot.delete_message = AsyncMock(return_value=True)
    ctx.bot.send_message = AsyncMock(return_value=types.SimpleNamespace(message_id=7))
    ctx.bot.ban_chat_member = AsyncMock(return_value=True)
    ctx.bot.get_chat_member = AsyncMock(
        return_value=types.SimpleNamespace(status="member",
                                           user=objetivo.from_user))
    ctx.bot_data = {"db": db, "cfg": _cfg(shadow, ttl), "notifier": None}
    ctx.application.job_queue = None
    return upd, ctx, db


@pytest.mark.asyncio
async def test_con_reply_borra_el_mensaje_del_spammer(tmp_path):
    """Banear al spammer y dejar su spam a la vista no tiene sentido."""
    upd, ctx, _ = _setup(tmp_path, ["publicidad"])
    await admin.cmd_ban(upd, ctx)
    borrados = {c.kwargs.get("message_id") for c in ctx.bot.delete_message.await_args_list}
    assert 4242 in borrados, f"no borró el mensaje baneado: {borrados}"


@pytest.mark.asyncio
async def test_con_motivo_lo_publica_en_el_grupo(tmp_path):
    upd, ctx, _ = _setup(tmp_path, ["spam", "de", "cripto"])
    await admin.cmd_ban(upd, ctx)
    publicados = [c.kwargs for c in ctx.bot.send_message.await_args_list
                  if c.kwargs.get("chat_id") == -100100]
    assert publicados, "no publicó nada pese a haber motivo"
    texto = publicados[0]["text"]
    assert "spam de cripto" in texto, f"no cita el motivo: {texto}"
    assert "777" in texto, "no identifica a quién se baneó"
    assert "tg://user" not in texto, "enlace clicable al perfil del spammer (regla 6)"


@pytest.mark.asyncio
async def test_sin_motivo_sigue_siendo_silencioso(tmp_path):
    """Coherente con «baneos silenciosos en el grupo por defecto»."""
    upd, ctx, _ = _setup(tmp_path, [])
    await admin.cmd_ban(upd, ctx)
    en_grupo = [c for c in ctx.bot.send_message.await_args_list
                if c.kwargs.get("chat_id") == -100100]
    assert not en_grupo, "publicó en el grupo sin que el admin diera un motivo"


@pytest.mark.asyncio
async def test_en_shadow_no_toca_el_grupo(tmp_path):
    """Modo prueba: ni borra ni publica."""
    upd, ctx, _ = _setup(tmp_path, ["motivo"], shadow=True)
    await admin.cmd_ban(upd, ctx)
    borrados = {c.kwargs.get("message_id") for c in ctx.bot.delete_message.await_args_list}
    assert 4242 not in borrados, "borró el mensaje estando en shadow"
    en_grupo = [c for c in ctx.bot.send_message.await_args_list
                if c.kwargs.get("chat_id") == -100100]
    assert not en_grupo, "publicó en el grupo estando en shadow"


def test_el_aviso_es_permanente_por_defecto():
    """0 = no se programa borrado. Si te molestaste en escribir el motivo, queda."""
    from src.config import load_config
    import os
    os.environ.pop("BAN_NOTICE_DELETE_AFTER_S", None)
    assert load_config().ban_notice_delete_after_s == 0
