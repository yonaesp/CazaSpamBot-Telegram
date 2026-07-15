"""Tests de la limpieza en grupos: ocultar comandos, auto-borrado y panel /limpieza."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import BotCommandScopeAllGroupChats

from src import group_clean as gc


# ------------------------------ prefs ------------------------------

def test_prefs_default_on(tmp_db):
    assert gc.hide_on(tmp_db) is True
    assert gc.clean_on(tmp_db) is True


def test_set_prefs(tmp_db):
    gc.set_hide(tmp_db, False)
    gc.set_clean(tmp_db, False)
    assert gc.hide_on(tmp_db) is False
    assert gc.clean_on(tmp_db) is False


# ------------------------ auto-borrado de comandos ------------------------

def _msg_ctx(db, text):
    bot = SimpleNamespace(delete_message=AsyncMock())
    msg = SimpleNamespace(text=text, caption=None, chat_id=-100, message_id=7)
    update = SimpleNamespace(effective_message=msg)
    context = SimpleNamespace(bot=bot, bot_data={"db": db, "command_names": {"config", "sync", "ban"}})
    return update, context, bot


@pytest.mark.asyncio
async def test_borra_comando_del_bot(tmp_db):
    update, context, bot = _msg_ctx(tmp_db, "/config")
    await gc.on_group_command_message(update, context)
    bot.delete_message.assert_awaited_once_with(chat_id=-100, message_id=7)


@pytest.mark.asyncio
async def test_borra_comando_con_arroba_y_args(tmp_db):
    update, context, bot = _msg_ctx(tmp_db, "/sync@CazaSpamBot off")
    await gc.on_group_command_message(update, context)
    bot.delete_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_borra_comando_ajeno(tmp_db):
    """Comando que no es del bot (p.ej. de otro bot) NO se toca."""
    update, context, bot = _msg_ctx(tmp_db, "/otracosa")
    await gc.on_group_command_message(update, context)
    bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_borra_si_clean_off(tmp_db):
    gc.set_clean(tmp_db, False)
    update, context, bot = _msg_ctx(tmp_db, "/config")
    await gc.on_group_command_message(update, context)
    bot.delete_message.assert_not_awaited()


# ------------------------ menú de comandos ------------------------

@pytest.mark.asyncio
async def test_apply_menu_oculta_en_grupos_por_defecto(tmp_db):
    bot = SimpleNamespace(set_my_commands=AsyncMock())
    cfg = SimpleNamespace(admin_user_id=999)
    await gc.apply_command_menu(bot, cfg, tmp_db)  # hide ON por defecto
    assert bot.set_my_commands.await_count == 3   # default + admin + grupos
    grp = [c for c in bot.set_my_commands.await_args_list
           if isinstance(c.kwargs.get("scope"), BotCommandScopeAllGroupChats)]
    assert grp and grp[0].args[0] == []           # grupos → lista vacía (ocultos)


@pytest.mark.asyncio
async def test_apply_menu_muestra_en_grupos_si_hide_off(tmp_db):
    gc.set_hide(tmp_db, False)
    bot = SimpleNamespace(set_my_commands=AsyncMock())
    cfg = SimpleNamespace(admin_user_id=999)
    await gc.apply_command_menu(bot, cfg, tmp_db)
    grp = [c for c in bot.set_my_commands.await_args_list
           if isinstance(c.kwargs.get("scope"), BotCommandScopeAllGroupChats)]
    assert grp and len(grp[0].args[0]) == len(gc._PUBLIC_MENU)   # público visible


# ------------------------ panel /limpieza ------------------------

@pytest.mark.asyncio
async def test_clean_callback_toggle_autodel(tmp_db):
    q = SimpleNamespace(data="clean:autodel", from_user=SimpleNamespace(id=999),
                        answer=AsyncMock(), edit_message_reply_markup=AsyncMock())
    update = SimpleNamespace(callback_query=q)
    context = SimpleNamespace(bot=SimpleNamespace(set_my_commands=AsyncMock()),
                              bot_data={"cfg": SimpleNamespace(admin_user_id=999), "db": tmp_db})
    await gc.on_clean_callback(update, context)
    assert gc.clean_on(tmp_db) is False           # era True → toggled
    q.edit_message_reply_markup.assert_awaited_once()


@pytest.mark.asyncio
async def test_clean_callback_hide_reaplica_menu(tmp_db):
    bot = SimpleNamespace(set_my_commands=AsyncMock())
    q = SimpleNamespace(data="clean:hide", from_user=SimpleNamespace(id=999),
                        answer=AsyncMock(), edit_message_reply_markup=AsyncMock())
    update = SimpleNamespace(callback_query=q)
    context = SimpleNamespace(bot=bot, bot_data={"cfg": SimpleNamespace(admin_user_id=999), "db": tmp_db})
    await gc.on_clean_callback(update, context)
    assert gc.hide_on(tmp_db) is False
    bot.set_my_commands.assert_awaited()          # re-publicó el menú


@pytest.mark.asyncio
async def test_clean_callback_solo_admin(tmp_db):
    q = SimpleNamespace(data="clean:autodel", from_user=SimpleNamespace(id=12345),
                        answer=AsyncMock(), edit_message_reply_markup=AsyncMock())
    update = SimpleNamespace(callback_query=q)
    context = SimpleNamespace(bot=SimpleNamespace(), bot_data={"cfg": SimpleNamespace(admin_user_id=999), "db": tmp_db})
    await gc.on_clean_callback(update, context)
    assert gc.clean_on(tmp_db) is True            # sin cambios
