"""Tests del modo LIMPIO por defecto: verificación/bienvenida OFF + revisión de
sospechosos por privado ON, y el anti-ruido de la revisión (_is_review_worthy).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import verification as v


# --------------------------- default de la DB ---------------------------

def test_ensure_chat_settings_default_limpio(tmp_db):
    """Un chat nuevo nace con verificación OFF y revisión de sospechosos ON."""
    tmp_db.ensure_chat_settings(-100777)
    s = tmp_db.get_chat_settings(-100777)
    assert s["verification_enabled"] == 0
    assert s["verification_review_suspicious"] == 1


# --------------------------- anti-ruido de la revisión ---------------------------

def test_review_worthy_solo_sin_username_no_dispara():
    """Sin @username a secas NO merece aviso (muchos legítimos no tienen)."""
    worthy, _ = v._is_review_worthy(None, username=None, first_name="Pepe", last_name="Lopez")
    assert worthy is False


def test_review_worthy_nombre_no_latino_dispara():
    worthy, reasons = v._is_review_worthy(None, username="ivan", first_name="Иван", last_name=None)
    assert worthy is True
    assert any("no-latino" in r for r in reasons)


def test_review_worthy_sin_foto_dispara():
    sig = SimpleNamespace(photo_count=0, account_age_days=500)
    worthy, _ = v._is_review_worthy(sig, username="ana", first_name="Ana", last_name=None)
    assert worthy is True


def test_review_worthy_dos_señales_debiles_dispara():
    """Dos indicios débiles acumulados sí (sin username + sin first_name)."""
    worthy, _ = v._is_review_worthy(None, username=None, first_name=None, last_name=None)
    assert worthy is True


# --------------------------- on_join con el default limpio ---------------------------

def _ctx(tmp_db, admin_notify=555):
    cfg = SimpleNamespace(shadow=False, admin_notify_chat_id=admin_notify, admin_user_id=999)
    bot = SimpleNamespace(restrict_chat_member=AsyncMock(), send_message=AsyncMock())
    return SimpleNamespace(
        bot=bot, bot_data={"cfg": cfg, "db": tmp_db},
        application=SimpleNamespace(job_queue=None),
    )


@pytest.mark.asyncio
async def test_on_join_limpio_no_sospechoso_entra_silencioso(tmp_db):
    """Default: usuario normal entra sin bienvenida, sin verificación, sin aviso."""
    tmp_db.ensure_chat_settings(-100)
    ctx = _ctx(tmp_db)
    chat = SimpleNamespace(id=-100, title="G")
    user = SimpleNamespace(id=5, username="pepe", first_name="Pepe", last_name="Lopez", is_premium=False)
    await v.on_join(update=None, context=ctx, chat=chat, user=user)
    ctx.bot.restrict_chat_member.assert_awaited()   # se desmutea (entra)
    ctx.bot.send_message.assert_not_awaited()        # NADA en el grupo ni aviso


@pytest.mark.asyncio
async def test_on_join_limpio_sospechoso_avisa_por_privado(tmp_db):
    """Default: perfil dudoso (nombre no-latino) → aviso privado al admin, nada en grupo."""
    tmp_db.ensure_chat_settings(-100)
    ctx = _ctx(tmp_db, admin_notify=555)
    chat = SimpleNamespace(id=-100, title="G")
    user = SimpleNamespace(id=7, username="x", first_name="Иван", last_name=None, is_premium=False)
    await v.on_join(update=None, context=ctx, chat=chat, user=user)
    ctx.bot.restrict_chat_member.assert_awaited()    # unmute (entra permitido)
    ctx.bot.send_message.assert_awaited_once()        # aviso de revisión
    assert ctx.bot.send_message.await_args.kwargs["chat_id"] == 555
