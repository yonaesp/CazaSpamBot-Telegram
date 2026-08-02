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


def _ctx(con_cola=True):
    ctx = MagicMock()
    ctx.bot.delete_message = AsyncMock(return_value=True)
    return ctx


def _borrados(ctx):
    return [(c.kwargs["chat_id"], c.kwargs["message_id"])
            for c in ctx.bot.delete_message.await_args_list]


@pytest.mark.asyncio
async def test_borra_la_bienvenida_del_modo_limpio(tmp_path):
    """El agujero principal: sin verificación no había rastro del mensaje."""
    db = _db(tmp_path)
    db.record_message(-100100, 777, "pepe")
    db.set_welcome_msg(-100100, 777, 4242)

    ctx = _ctx()
    n = await verification.limpiar_bienvenidas(ctx, db, 777)
    assert n == 1, "no borró la bienvenida"
    assert _borrados(ctx) == [(-100100, 4242)]
    assert db.welcomes_pendientes(777) == [], "no soltó el registro tras borrar"


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
    assert set(_borrados(ctx)) == {(-100100, 11), (-100101, 22)}


@pytest.mark.asyncio
async def test_tambien_borra_la_del_flujo_de_verificacion(tmp_path):
    db = _db(tmp_path)
    db.add_pending_verification(chat_id=-100100, user_id=777,
                                welcome_msg_id=555, is_suspicious=False)
    ctx = _ctx()
    n = await verification.limpiar_bienvenidas(ctx, db, 777)
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
    assert len(_borrados(ctx)) == 1


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


@pytest.mark.asyncio
async def test_si_el_borrado_falla_se_conserva_para_reintentar(tmp_path):
    """Soltar el registro tras un fallo dejaría el saludo en el grupo para siempre
    y sin rastro. Conservándolo, el barrido del cleanup_job lo reintenta."""
    from telegram.error import TelegramError
    db = _db(tmp_path)
    db.record_message(-100100, 777, "pepe")
    db.set_welcome_msg(-100100, 777, 4242)
    ctx = _ctx()
    ctx.bot.delete_message = AsyncMock(side_effect=TelegramError("sin permisos"))

    n = await verification.limpiar_bienvenidas(ctx, db, 777)
    assert n == 0
    assert db.welcomes_pendientes(777) == [(-100100, 4242)], (
        "soltó el registro pese a no haber podido borrar")


@pytest.mark.asyncio
async def test_el_barrido_caza_las_que_sobrevivan_a_un_reinicio(tmp_path):
    """El job vive en memoria: un reinicio dentro de ese minuto lo pierde y el
    saludo se quedaría para siempre dando la bienvenida a un expulsado."""
    db = _db(tmp_path)
    db.record_message(-100100, 777, "pepe")
    db.set_welcome_msg(-100100, 777, 4242)
    db.add_ban(user_id=777, reason="x", rule="r", banned_in_chat=-100100, federated=True)

    pendientes = db.bienvenidas_de_baneados()
    assert (-100100, 777, 4242) in pendientes, "el barrido no la ve"


@pytest.mark.asyncio
async def test_el_barrido_no_toca_la_bienvenida_de_alguien_legitimo(tmp_path):
    """Contrapeso: solo bienvenidas de usuarios BANEADOS."""
    db = _db(tmp_path)
    db.record_message(-100100, 888, "legitimo")
    db.set_welcome_msg(-100100, 888, 555)
    assert db.bienvenidas_de_baneados() == [], "borraría el saludo de un usuario normal"
