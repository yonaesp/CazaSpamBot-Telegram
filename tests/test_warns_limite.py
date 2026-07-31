"""El límite de warns y la sanción al alcanzarlo.

Aquí vivía un bug de producción sin cubrir: `sancion_ok` solo se asignaba en las
ramas de kick y mute, así que con la acción POR DEFECTO (ban) la lectura posterior
lanzaba NameError. El ban se ejecutaba, pero el contador no se reseteaba, el grupo
no veía el aviso y al admin le llegaba un «error interno del bot».

También se comprueba que el botón «⚠️ Avisar» del aviso de usuario de confianza
hace lo MISMO que /warn, que era la otra mitad del problema: antes solo apuntaba
el warn en la base de datos y nadie se enteraba.
"""
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import warns_mod
from src.db import DB


def _ctx(tmp_path, accion="ban", limite=3):
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(-100100, "G", "supergroup", True, True, True)
    db.ensure_chat_settings(-100100)
    if accion:
        db.update_chat_setting(-100100, "warns_action", accion)
    db.update_chat_setting(-100100, "warns_limit", limite)
    cfg = types.SimpleNamespace(shadow=False, admin_user_id=1, federation_enabled=True,
                                public_quip_delete_after_s=0)
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock(return_value=types.SimpleNamespace(message_id=9))
    ctx.bot.delete_message = AsyncMock()
    ctx.bot.ban_chat_member = AsyncMock()
    ctx.bot.unban_chat_member = AsyncMock()
    ctx.bot.restrict_chat_member = AsyncMock()
    ctx.bot_data = {"db": db, "cfg": cfg}
    ctx.application.job_queue = None
    return ctx, db


@pytest.mark.asyncio
async def test_llegar_al_limite_con_la_accion_por_defecto_no_revienta(tmp_path):
    """Regresión del NameError. `warnaction=ban` es el valor por defecto, así que
    esto le pasaba a cualquiera que usara /warn sin tocar la configuración."""
    ctx, db = _ctx(tmp_path, accion="ban", limite=3)
    for _ in range(3):
        n = await warns_mod.aplicar_warn(ctx, chat_id=-100100, target_id=777,
                                         target_user=None, by_admin=1, reason="x")
    assert n == 3
    assert db.is_banned(777), "no llegó a banear al alcanzar el límite"
    assert db.list_warns(777, -100100) == [] or len(db.list_warns(777, -100100)) == 0, (
        "el contador no se reseteó tras la sanción"
    )
    assert ctx.bot.send_message.await_count == 3, "el grupo no vio los avisos"


@pytest.mark.asyncio
async def test_por_debajo_del_limite_solo_cuenta(tmp_path):
    ctx, db = _ctx(tmp_path, accion="ban", limite=3)
    n = await warns_mod.aplicar_warn(ctx, chat_id=-100100, target_id=777,
                                     target_user=None, by_admin=1, reason=None)
    assert n == 1
    assert not db.is_banned(777), "baneó con un solo warn"
    assert ctx.bot.send_message.await_count == 1, "no publicó el contador en el grupo"


@pytest.mark.asyncio
async def test_si_la_sancion_falla_el_contador_NO_se_resetea(tmp_path):
    """Si el kick falla (sin permisos, target owner), el grupo veía «Kick» y el
    contador volvía a 0 sin haber sancionado a nadie."""
    from telegram.error import TelegramError
    ctx, db = _ctx(tmp_path, accion="kick", limite=2)
    ctx.bot.ban_chat_member = AsyncMock(side_effect=TelegramError("sin permisos"))
    for _ in range(2):
        await warns_mod.aplicar_warn(ctx, chat_id=-100100, target_id=777,
                                     target_user=None, by_admin=1, reason=None)
    assert len(db.list_warns(777, -100100)) == 2, "reseteó los warns sin haber sancionado"


@pytest.mark.asyncio
async def test_el_boton_avisar_hace_lo_mismo_que_warn(tmp_path):
    """El botón del aviso de usuario de confianza: publica, borra y cuenta."""
    from src import handlers
    ctx, db = _ctx(tmp_path, accion="ban", limite=3)
    ctx.bot.get_chat_member = AsyncMock(
        return_value=types.SimpleNamespace(user=types.SimpleNamespace(
            id=777, username="pepe", first_name="Pepe")))
    q = MagicMock()
    q.from_user = types.SimpleNamespace(id=1)
    q.data = "tnote:warn:-100100:777:42"
    q.answer = AsyncMock()
    q.edit_message_reply_markup = AsyncMock()
    upd = MagicMock()
    upd.callback_query = q

    await handlers.on_trust_notice_callback(upd, ctx)

    assert ctx.bot.send_message.await_count == 1, "el grupo no se enteró del warn"
    assert len(db.list_warns(777, -100100)) == 1, "no registró el warn"
    assert ctx.bot.delete_message.await_count >= 1, "no borró el mensaje señalado"
    filas = db.recent_actions(limit=1)
    assert filas and filas[0]["action"] == "warn", "el warn no quedó en la auditoría"
