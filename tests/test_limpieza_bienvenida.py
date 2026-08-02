"""Al banear a alguien recién llegado, su bienvenida tiene que desaparecer.

Caso real: un admin banea a un usuario que acaba de entrar y el saludo se queda
en el grupo, dando la bienvenida a alguien ya expulsado.

Había tres agujeros:
  1. El welcome del MODO LIMPIO (el que viene por defecto, sin verificación) no
     guardaba su id en ningún sitio, así que no había nada que borrar.
  2. Tras verificar, la fila de `pending_verifications` se limpia, y a partir de
     ahí un ban posterior tampoco sabía qué borrar.
  3. El ban hecho a mano desde la app de Telegram no pasa por ningún comando del
     bot, así que no limpiaba nada en absoluto.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import verification
from src.db import DB


def _db(tmp_path, n_chats=2):
    db = DB(str(tmp_path / "t.db"))
    for i in range(n_chats):
        cid = -100100 - i
        db.upsert_bot_chat(cid, f"G{i}", "supergroup", True, True, True)
        db.ensure_chat_settings(cid)
    return db


def _ctx():
    ctx = MagicMock()
    ctx.bot.delete_message = AsyncMock(return_value=True)
    return ctx


@pytest.mark.asyncio
async def test_borra_la_bienvenida_del_modo_limpio(tmp_path):
    """El agujero principal: sin verificación no había rastro del mensaje."""
    db = _db(tmp_path)
    db.record_message(-100100, 777, "pepe")
    db.set_welcome_msg(-100100, 777, 4242)

    n = await verification.limpiar_bienvenidas(_ctx(), db, 777)
    assert n == 1, "no borró la bienvenida"
    assert db.welcomes_pendientes(777) == [], "no limpió el registro"


@pytest.mark.asyncio
async def test_borra_en_todos_los_grupos(tmp_path):
    """El bot es federado: puede haberle dado la bienvenida en varios sitios."""
    db = _db(tmp_path)
    for cid, mid in ((-100100, 11), (-100101, 22)):
        db.record_message(cid, 777, "pepe")
        db.set_welcome_msg(cid, 777, mid)

    ctx = _ctx()
    n = await verification.limpiar_bienvenidas(ctx, db, 777)
    assert n == 2
    borrados = {c.kwargs["message_id"] for c in ctx.bot.delete_message.await_args_list}
    assert borrados == {11, 22}


@pytest.mark.asyncio
async def test_tambien_borra_la_del_flujo_de_verificacion(tmp_path):
    db = _db(tmp_path)
    db.add_pending_verification(chat_id=-100100, user_id=777,
                                welcome_msg_id=555, is_suspicious=False)
    n = await verification.limpiar_bienvenidas(_ctx(), db, 777)
    assert n == 1
    assert db.get_pending(-100100, 777) is None, "dejó la fila pendiente colgada"


@pytest.mark.asyncio
async def test_no_borra_dos_veces_el_mismo_mensaje(tmp_path):
    """El id puede estar en los dos sitios a la vez: una sola llamada a Telegram."""
    db = _db(tmp_path)
    db.record_message(-100100, 777, "pepe")
    db.set_welcome_msg(-100100, 777, 999)
    db.add_pending_verification(chat_id=-100100, user_id=777,
                                welcome_msg_id=999, is_suspicious=False)
    ctx = _ctx()
    n = await verification.limpiar_bienvenidas(ctx, db, 777)
    assert n == 1, f"borró el mismo mensaje {n} veces"
    assert ctx.bot.delete_message.await_count == 1


@pytest.mark.asyncio
async def test_un_fallo_de_telegram_no_interrumpe_el_ban(tmp_path):
    """El mensaje puede estar ya borrado, o faltar permisos. El ban manda."""
    from telegram.error import TelegramError
    db = _db(tmp_path)
    for cid, mid in ((-100100, 11), (-100101, 22)):
        db.record_message(cid, 777, "pepe")
        db.set_welcome_msg(cid, 777, mid)
    ctx = _ctx()
    ctx.bot.delete_message = AsyncMock(side_effect=[TelegramError("ya borrado"), True])
    n = await verification.limpiar_bienvenidas(ctx, db, 777)
    assert n == 1, "un fallo en el primero impidió borrar el segundo"


@pytest.mark.asyncio
async def test_sin_bienvenida_no_hace_nada(tmp_path):
    db = _db(tmp_path)
    db.record_message(-100100, 777, "pepe")
    ctx = _ctx()
    assert await verification.limpiar_bienvenidas(ctx, db, 777) == 0
    assert ctx.bot.delete_message.await_count == 0


def test_todos_los_caminos_de_ban_la_llaman():
    """Los cuatro: /ban, el combo de /spam, la regla automática y el ban a mano
    desde la app de Telegram. Este último era el que no limpiaba nada."""
    import pathlib
    admin_src = pathlib.Path("src/admin.py").read_text()
    handlers_src = pathlib.Path("src/handlers.py").read_text()
    assert "limpiar_bienvenidas" in admin_src, "/ban y /spam no limpian"
    assert handlers_src.count("limpiar_bienvenidas") >= 2, (
        "faltan caminos en handlers: el automático y/o el ban manual de Telegram"
    )
