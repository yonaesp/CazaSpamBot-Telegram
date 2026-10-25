"""Un aviso suave que el autor corrige editando se da por resuelto en silencio.

Petición del admin (25-oct-2026): si alguien de confianza menciona a un externo o
pone un enlace, le llega «Algo raro de alguien de confianza» por privado; si
después lo corrige editando, ese privado se actualiza (editar no avisa) y el aviso
del grupo se borra. Se edita en vez de borrarse para no hacer desaparecer algo ya
leído y para conservar lo que decía, por si era una cuenta robada borrando el rastro.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import handlers

CHAT, MID, UID, ADMIN = -1001156069668, 451500, 1047674290, 777
ANTES = "Mirad este grupo t.me/otro_grupo_de_domotica"


def _msg(texto="Mirad este grupo (enlace quitado)"):
    return NS(text=texto, caption=None, chat_id=CHAT, message_id=MID,
              chat=NS(id=CHAT, title="Domótica", username="AlexaEsp", type="supergroup"))


def _ctx():
    ctx = MagicMock()
    ctx.bot.edit_message_text = AsyncMock()
    ctx.bot.delete_message = AsyncMock()
    return ctx


_USER = NS(id=UID, first_name="Juan M.", username="BubitoFilms")


@pytest.mark.asyncio
async def test_corregido_edita_el_privado_y_borra_el_aviso_del_grupo(tmp_db):
    tmp_db.add_gentle_warning(CHAT, MID, 9100, UID)
    tmp_db.guardar_aviso_admin(CHAT, MID, ADMIN, 5000, 9100, ANTES)
    ctx = _ctx()
    await handlers._aviso_resuelto_al_editar(ctx, tmp_db, _msg(), _USER)

    kw = ctx.bot.edit_message_text.await_args.kwargs
    assert (kw["chat_id"], kw["message_id"]) == (ADMIN, 5000)
    assert kw["reply_markup"] is None                     # ya no hay nada que decidir
    assert "Corregido por su autor" in kw["text"]
    assert ANTES in kw["text"]                            # la prueba se conserva
    assert "t.me/AlexaEsp/451500" in kw["text"]
    ctx.bot.delete_message.assert_awaited_once_with(chat_id=CHAT, message_id=9100)
    assert not tmp_db.hay_aviso_admin(CHAT, MID)
    assert tmp_db.pop_gentle_warning_by_user_msg(CHAT, MID) is None


@pytest.mark.asyncio
async def test_sin_aviso_previo_no_hace_nada(tmp_db):
    ctx = _ctx()
    await handlers._aviso_resuelto_al_editar(ctx, tmp_db, _msg(), _USER)
    ctx.bot.edit_message_text.assert_not_awaited()
    ctx.bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_toca_otro_aviso_del_mismo_mensaje(tmp_db):
    """Si la fila del grupo ya es de otro aviso (p. ej. una errata), se respeta."""
    tmp_db.add_gentle_warning(CHAT, MID, 9200, UID, errata=[["Moliko", "Molkio"]])
    tmp_db.guardar_aviso_admin(CHAT, MID, ADMIN, 5000, 9100, ANTES)
    await handlers._aviso_resuelto_al_editar(_ctx(), tmp_db, _msg(), _USER)
    assert tmp_db.errata_pendiente(CHAT, MID) == (9200, [["Moliko", "Molkio"]])


@pytest.mark.asyncio
async def test_si_ya_decidiste_no_se_reescribe(tmp_db):
    tmp_db.guardar_aviso_admin(CHAT, MID, ADMIN, 5000, 9100, ANTES)
    q = MagicMock()
    q.from_user.id = ADMIN
    q.data = f"tnote:nada:{CHAT}:{UID}:{MID}"
    q.answer = AsyncMock()
    q.edit_message_reply_markup = AsyncMock()
    ctx = _ctx()
    ctx.bot_data = {"cfg": NS(admin_user_id=ADMIN, shadow=False), "db": tmp_db}
    await handlers.on_trust_notice_callback(NS(callback_query=q), ctx)
    assert not tmp_db.hay_aviso_admin(CHAT, MID)
    await handlers._aviso_resuelto_al_editar(ctx, tmp_db, _msg(), _USER)
    ctx.bot.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_el_aviso_devuelve_su_id(monkeypatch):
    monkeypatch.setattr(handlers.notify_prefs, "effective", lambda *a, **k: True)
    bot = NS(send_message=AsyncMock(return_value=NS(message_id=5000)))
    ctx = NS(bot=bot, bot_data={}, application=NS(job_queue=None))
    aviso = await handlers._send_trust_notice(
        ctx, object(), NS(admin_notify_chat_id=ADMIN, mode="active"), _msg(ANTES), _USER,
        ["external_mention_or_link"], "Enlace a 1 chat externo", "gentle_warn", 90)
    assert aviso == 5000


def test_solo_el_aviso_suave_se_puede_dar_por_resuelto():
    """Lo que el bot habría baneado no se da por bueno porque se edite: solo el
    camino del aviso suave guarda el privado en `avisos_admin`."""
    fuente = inspect.getsource(handlers)
    assert fuente.count("db.guardar_aviso_admin(") == 1
    bloque = inspect.getsource(handlers.on_message)
    i = bloque.index("db.guardar_aviso_admin(")
    assert 'proposed_action="gentle_warn"' in bloque[i - 600:i]
    # Una edición que sigue igual no repite el aviso, y la que lo corrige lo resuelve
    assert "is_edit and db.hay_aviso_admin(" in bloque
    assert "if is_edit:\n            await _aviso_resuelto_al_editar(" in bloque
