"""Quips por chat: herencia del .env, botón del panel y comando /quips.

El punto delicado es la HERENCIA: `chat_settings.quips_enabled` nace NULL y ese NULL
significa «hereda PUBLIC_QUIP_ENABLED del .env», no «apagado». Si el panel lo leyera
como un booleano normal enseñaría OFF a quien tiene los quips funcionando.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import config_panel as cp
from src import quips

ADMIN = 999
CID = -100123


def _cfg(quips_on: bool):
    return SimpleNamespace(admin_user_id=ADMIN, public_quip_enabled=quips_on)


# --------------------------- herencia del .env ---------------------------

@pytest.mark.parametrize("env_on", [True, False])
def test_columna_null_hereda_el_env(tmp_db, env_on):
    tmp_db.ensure_chat_settings(CID)
    assert tmp_db.get_chat_settings(CID)["quips_enabled"] is None  # nace sin decidir
    assert quips.quips_on(tmp_db, CID, _cfg(env_on)) is env_on


@pytest.mark.parametrize("col,esperado", [(0, False), (1, True)])
def test_columna_fijada_manda_sobre_el_env(tmp_db, col, esperado):
    """Con la columna puesta, el .env deja de pintar nada (en ambos sentidos)."""
    tmp_db.ensure_chat_settings(CID)
    tmp_db.update_chat_setting(CID, "quips_enabled", col)
    assert quips.quips_on(tmp_db, CID, _cfg(True)) is esperado
    assert quips.quips_on(tmp_db, CID, _cfg(False)) is esperado


def test_chat_desconocido_cae_al_env(tmp_db):
    """Un chat sin fila de settings no debe romper: manda el .env."""
    assert quips.quips_on(tmp_db, -55555, _cfg(True)) is True


def test_db_rota_no_tumba_el_ban():
    """El quip es cosmético: si la BD falla se responde con el .env, sin excepción."""
    db = MagicMock()
    db.get_chat_settings.side_effect = RuntimeError("BD ocupada")
    assert quips.quips_on(db, CID, _cfg(True)) is True


# ------------------------------ botón del panel ------------------------------

def _boton_quips(kb):
    return next(b for row in kb.inline_keyboard for b in row
                if b.callback_data == f"cfg:quips:{CID}")


def test_panel_muestra_on_cuando_se_hereda_del_env(tmp_db):
    """El fallo a evitar: columna NULL + .env ON debe pintarse ON, no OFF."""
    tmp_db.ensure_chat_settings(CID)
    s = tmp_db.get_chat_settings(CID)
    estado = cp._quips_state(tmp_db, _cfg(True), CID)
    kb = cp.build_panel_keyboard(CID, s, False, estado)
    assert "✅ ON" in _boton_quips(kb).text


def test_panel_muestra_off_cuando_el_env_esta_off(tmp_db):
    tmp_db.ensure_chat_settings(CID)
    s = tmp_db.get_chat_settings(CID)
    estado = cp._quips_state(tmp_db, _cfg(False), CID)
    kb = cp.build_panel_keyboard(CID, s, False, estado)
    assert "❌ OFF" in _boton_quips(kb).text


def test_panel_columna_apagada_gana_al_env(tmp_db):
    tmp_db.ensure_chat_settings(CID)
    tmp_db.update_chat_setting(CID, "quips_enabled", 0)
    s = tmp_db.get_chat_settings(CID)
    kb = cp.build_panel_keyboard(CID, s, False, cp._quips_state(tmp_db, _cfg(True), CID))
    assert "❌ OFF" in _boton_quips(kb).text


def test_inherited_detecta_null_y_valor(tmp_db):
    tmp_db.ensure_chat_settings(CID)
    assert cp._quips_inherited(tmp_db.get_chat_settings(CID)) is True
    tmp_db.update_chat_setting(CID, "quips_enabled", 1)
    assert cp._quips_inherited(tmp_db.get_chat_settings(CID)) is False


def test_texto_de_la_vista_distingue_heredado_de_propio():
    heredado = cp._quips_text(True, inherited=True)
    propio = cp._quips_text(True, inherited=False)
    assert heredado != propio
    assert "heredado" in heredado.lower()


# ------------------------------ previsualización ------------------------------

def _cbctx(db, cfg, user_id=ADMIN):
    q = SimpleNamespace(
        data=None,
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        message=SimpleNamespace(chat_id=ADMIN),
    )
    update = SimpleNamespace(callback_query=q)
    context = SimpleNamespace(bot_data={"cfg": cfg, "db": db}, user_data={},
                              bot=SimpleNamespace(send_message=AsyncMock()))
    return update, context, q


@pytest.mark.asyncio
async def test_boton_quips_previsualiza_sin_tocar_el_ajuste(tmp_db):
    """Pulsar el botón abre la vista con un ejemplo; NO cambia nada todavía."""
    tmp_db.ensure_chat_settings(CID)
    db = MagicMock(wraps=tmp_db)
    db.get_chat_settings.side_effect = tmp_db.get_chat_settings
    db.all_chats.return_value = [{"chat_id": CID, "title": "Grupo", "am_admin": True}]
    update, context, q = _cbctx(db, _cfg(True))
    q.data = f"cfg:quips:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()
    texto = q.edit_message_text.await_args.args[0]
    assert str(quips.DEMO_USER_ID) in texto          # el ejemplo es de mentira
    kb = q.edit_message_text.await_args.kwargs["reply_markup"]
    datos = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert f"cfg:qset:1:{CID}" in datos and f"cfg:qset:0:{CID}" in datos


@pytest.mark.asyncio
async def test_qset_escribe_el_ajuste(tmp_db):
    tmp_db.ensure_chat_settings(CID)
    db = MagicMock(wraps=tmp_db)
    db.get_chat_settings.side_effect = tmp_db.get_chat_settings
    db.get_pref.return_value = False  # sync OFF: solo este grupo
    db.all_chats.return_value = [{"chat_id": CID, "title": "Grupo", "am_admin": True}]
    update, context, q = _cbctx(db, _cfg(True))
    q.data = f"cfg:qset:0:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "quips_enabled", 0)


@pytest.mark.asyncio
async def test_qset_con_sync_on_aplica_a_todos_los_grupos(tmp_db):
    db = MagicMock(wraps=tmp_db)
    db.get_chat_settings.side_effect = tmp_db.get_chat_settings
    db.get_pref.return_value = None  # sync ON por defecto
    db.all_chats.return_value = [
        {"chat_id": -1, "title": "A", "am_admin": True},
        {"chat_id": -2, "title": "B", "am_admin": True},
    ]
    update, context, q = _cbctx(db, _cfg(False))
    q.data = f"cfg:qset:1:{CID}"
    await cp.on_callback(update, context)
    escritos = {c.args for c in db.update_chat_setting.call_args_list}
    assert (-1, "quips_enabled", 1) in escritos
    assert (-2, "quips_enabled", 1) in escritos


@pytest.mark.asyncio
async def test_qset_valor_invalido_no_escribe(tmp_db):
    db = MagicMock(wraps=tmp_db)
    update, context, q = _cbctx(db, _cfg(True))
    q.data = f"cfg:qset:9:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()


@pytest.mark.asyncio
async def test_quips_solo_admin(tmp_db):
    db = MagicMock(wraps=tmp_db)
    update, context, q = _cbctx(db, _cfg(True), user_id=12345)
    q.data = f"cfg:qset:1:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()


# --------------------------------- /quips ---------------------------------

def _cmdctx(db, cfg, user_id=ADMIN, chat_type="private"):
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=ADMIN, type=chat_type),
        effective_message=SimpleNamespace(reply_text=reply),
    )
    context = SimpleNamespace(bot_data={"cfg": cfg, "db": db}, user_data={})
    return update, context, reply


@pytest.mark.asyncio
async def test_cmd_quips_muestra_varios_ejemplos(tmp_db):
    db = MagicMock(wraps=tmp_db)
    db.all_chats.return_value = [{"chat_id": CID, "title": "Grupo", "am_admin": True}]
    update, context, reply = _cmdctx(db, _cfg(True))
    await cp.cmd_quips(update, context)
    texto = reply.await_args.args[0]
    assert texto.count(str(quips.DEMO_USER_ID)) >= 3   # varias reglas distintas
    db.update_chat_setting.assert_not_called()         # no toca ningún ajuste


@pytest.mark.asyncio
async def test_cmd_quips_no_admin_calla(tmp_db):
    db = MagicMock(wraps=tmp_db)
    update, context, reply = _cmdctx(db, _cfg(True), user_id=1)
    await cp.cmd_quips(update, context)
    reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_quips_sin_catalogo_no_revienta(tmp_db, monkeypatch):
    """Reglas sin frases (idioma a medio traducir) → mensaje de respaldo, no excepción."""
    monkeypatch.setattr(quips, "_RULES", ("regla_inventada_sin_catalogo",))
    db = MagicMock(wraps=tmp_db)
    db.all_chats.return_value = []
    update, context, reply = _cmdctx(db, _cfg(True))
    await cp.cmd_quips(update, context)
    reply.assert_awaited_once()
    assert "{" not in reply.await_args.args[0]  # sin placeholders sin sustituir


def test_demo_samples_salta_reglas_sin_catalogo(monkeypatch):
    monkeypatch.setattr(quips, "_RULES", ("cas_match", "regla_inventada_sin_catalogo"))
    muestras = quips.demo_samples(4)
    assert [r for r, _ in muestras] == ["cas_match"]


def test_demo_samples_devuelve_reglas_distintas():
    muestras = quips.demo_samples(4)
    assert len(muestras) == 4
    assert len({r for r, _ in muestras}) == 4
    for _, frase in muestras:
        assert "{" not in frase and quips.DEMO_FIRST_NAME in frase


def test_demo_nunca_muestra_el_quip_de_unban():
    """El quip de unban celebra que alguien VUELVE. En una pantalla titulada
    «frases al banear» daba a entender que el bot readmite gente, así que se
    excluye de los ejemplos (sigue publicándose de verdad en un /unban real)."""
    for _ in range(30):
        assert "manual_admin_unban" not in {r for r, _ in quips.demo_samples(5)}
    # y sigue existiendo para su uso real
    assert quips.demo("manual_admin_unban")
