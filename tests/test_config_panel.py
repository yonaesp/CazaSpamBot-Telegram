"""Tests del panel de ajustes por botones (/config)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import config_panel as cp
from telegram import InlineKeyboardMarkup

ADMIN = 999
CID = -100123


def _settings(**over):
    base = {
        "verification_enabled": 1,
        "verification_review_suspicious": 0,
        "verification_reminders_enabled": 1,
        "verification_kick_normal": 1,
        "verification_suspicious_kick_minutes": 30,
        "verification_reminder_hours": 3,
        "verification_kick_after_reminder_hours": 6,
        "welcome_enabled": 1,
        "cleanservice": 1,
        "welcome_delete_after_s": 900,
        "warns_limit": 3,
        "warns_action": "ban",
        "topweekly_enabled": 0,
    }
    base.update(over)
    return base


def _db(settings=None, chats=None, buttons=None):
    db = MagicMock()
    db.get_chat_settings.return_value = settings if settings is not None else _settings()
    db.all_chats.return_value = chats if chats is not None else [
        {"chat_id": CID, "title": "Grupo Test", "am_admin": True},
    ]
    db.get_pref.return_value = None  # sync ON por defecto (config_sync sin fijar)
    db.list_welcome_buttons.return_value = buttons if buttons is not None else []
    db.get_welcome_button.return_value = None
    db.delete_welcome_buttons_like.return_value = 1
    return db


def _cbctx(db, user_id=ADMIN):
    cfg = SimpleNamespace(admin_user_id=ADMIN)
    q = SimpleNamespace(
        data=None,
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        message=SimpleNamespace(chat_id=ADMIN),
    )
    update = SimpleNamespace(callback_query=q)
    context = SimpleNamespace(
        bot_data={"cfg": cfg, "db": db},
        user_data={},
        bot=SimpleNamespace(send_message=AsyncMock()),
    )
    return update, context, q


# ------------------------------- teclados -------------------------------

def test_panel_keyboard_estado_en_etiquetas():
    kb = cp.build_panel_keyboard(CID, _settings(verification_enabled=0, welcome_enabled=1))
    flat = [b for row in kb.inline_keyboard for b in row]
    verif = next(b for b in flat if "Verificación" in b.text)
    assert "❌ OFF" in verif.text
    assert verif.callback_data == f"cfg:tog:verification_enabled:{CID}"
    welcome = next(b for b in flat if b.text.startswith("👋"))
    assert "✅ ON" in welcome.text


def test_panel_keyboard_accion_refleja_kick_mute():
    kb_kick = cp.build_panel_keyboard(CID, _settings(verification_kick_normal=1))
    kb_mute = cp.build_panel_keyboard(CID, _settings(verification_kick_normal=0))
    txt_kick = [b.text for row in kb_kick.inline_keyboard for b in row]
    txt_mute = [b.text for row in kb_mute.inline_keyboard for b in row]
    assert any("Expulsar" in t for t in txt_kick)
    assert any("Silenciar" in t for t in txt_mute)


def test_times_keyboard_marca_actual():
    kb = cp.build_times_keyboard(CID, _settings(verification_suspicious_kick_minutes=60))
    flat = [b for row in kb.inline_keyboard for b in row]
    sel = next(b for b in flat if b.callback_data == f"cfg:st:sk:60:{CID}")
    assert sel.text.startswith("✅")


# ------------------------------- callbacks -------------------------------

@pytest.mark.asyncio
async def test_toggle_invierte_campo():
    db = _db(_settings(cleanservice=1))
    update, context, q = _cbctx(db)
    q.data = f"cfg:tog:cleanservice:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "cleanservice", 0)
    q.edit_message_reply_markup.assert_awaited_once()


@pytest.mark.asyncio
async def test_accion_invierte_kick_normal():
    db = _db(_settings(verification_kick_normal=1))
    update, context, q = _cbctx(db)
    q.data = f"cfg:accion:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "verification_kick_normal", 0)


@pytest.mark.asyncio
async def test_set_tiempo_valido():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:st:rh:6:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "verification_reminder_hours", 6)


@pytest.mark.asyncio
async def test_set_tiempo_fuera_de_preset_rechazado():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:st:rh:99:{CID}"  # 99 no está en los presets
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()


@pytest.mark.asyncio
async def test_toggle_campo_no_permitido_rechazado():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:tog:warns_limit:{CID}"  # no está en _TOGGLE_FIELDS
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()


@pytest.mark.asyncio
async def test_guard_solo_admin():
    db = _db()
    update, context, q = _cbctx(db, user_id=12345)  # no admin
    q.data = f"cfg:tog:cleanservice:{CID}"
    await cp.on_callback(update, context)
    q.answer.assert_awaited_once()
    assert q.answer.await_args.kwargs.get("show_alert") is True
    db.update_chat_setting.assert_not_called()


@pytest.mark.asyncio
async def test_edit_muestra_selector_de_grupo():
    """Paso 1: 'Editar bienvenida' muestra el selector de grupo (aún sin captura)."""
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:edit:w:{CID}"
    await cp.on_callback(update, context)
    assert "cfg_await" not in context.user_data           # todavía no captura
    q.edit_message_text.assert_awaited_once()
    kb = q.edit_message_text.await_args.kwargs["reply_markup"]
    flat = [b for row in kb.inline_keyboard for b in row]
    assert any(b.callback_data == f"cfg:escope:w:all:{CID}" for b in flat)  # opción "Todos"


@pytest.mark.asyncio
async def test_escope_arma_captura_con_scope():
    """Paso 2: elegido el scope, se arma la captura con ese scope."""
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:escope:w:all:{CID}"
    await cp.on_callback(update, context)
    assert context.user_data["cfg_await"] == {"field": "welcome_text", "scope": "all"}
    q.edit_message_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_escope_grupo_individual():
    """Scope de un grupo concreto queda guardado como su chat_id."""
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:escope:w:{CID}:{CID}"
    await cp.on_callback(update, context)
    assert context.user_data["cfg_await"] == {"field": "welcome_text", "scope": str(CID)}


@pytest.mark.asyncio
async def test_capture_welcome_scope_all_escribe_en_todos():
    """Captura con scope 'all' escribe la bienvenida en todos los grupos moderados."""
    chats = [
        {"chat_id": -1, "title": "A", "am_admin": True},
        {"chat_id": -2, "title": "B", "am_admin": True},
    ]
    db = _db(chats=chats)
    context = SimpleNamespace(bot_data={"db": db},
                              user_data={"cfg_await": {"field": "welcome_text", "scope": "all"}})
    msg = SimpleNamespace(text="Hola {name} a {chat}", caption=None, reply_text=AsyncMock())
    update = SimpleNamespace(effective_message=msg)
    assert await cp.handle_capture(update, context) is True
    text_calls = {c.args for c in db.update_chat_setting.call_args_list}
    assert (-1, "welcome_text", "Hola {name} a {chat}") in text_calls
    assert (-2, "welcome_text", "Hola {name} a {chat}") in text_calls


# ------------------------------- captura -------------------------------

@pytest.mark.asyncio
async def test_capture_sin_pendiente_devuelve_false():
    db = _db()
    context = SimpleNamespace(bot_data={"db": db}, user_data={})
    update = SimpleNamespace(effective_message=SimpleNamespace(text="hola", caption=None,
                                                               reply_text=AsyncMock()))
    assert await cp.handle_capture(update, context) is False


@pytest.mark.asyncio
async def test_capture_welcome_guarda_y_parsea_botones():
    db = _db()
    context = SimpleNamespace(bot_data={"db": db},
                              user_data={"cfg_await": {"chat_id": CID, "field": "welcome_text"}})
    msg = SimpleNamespace(
        text="Hola {name} [Reglas](buttonurl://https://t.me/x)",
        caption=None, reply_text=AsyncMock(),
    )
    update = SimpleNamespace(effective_message=msg)
    consumed = await cp.handle_capture(update, context)
    assert consumed is True
    # texto guardado sin el botón Rose
    call = db.update_chat_setting.call_args
    assert call.args[0] == CID and call.args[1] == "welcome_text"
    assert "buttonurl" not in call.args[2] and "Hola {name}" in call.args[2]
    db.add_welcome_button.assert_called_once()
    assert "cfg_await" not in context.user_data  # un solo uso
    msg.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_capture_rules_guarda_texto_plano():
    db = _db()
    context = SimpleNamespace(bot_data={"db": db},
                              user_data={"cfg_await": {"chat_id": CID, "field": "rules_text"}})
    msg = SimpleNamespace(text="No spam.", caption=None, reply_text=AsyncMock())
    update = SimpleNamespace(effective_message=msg)
    assert await cp.handle_capture(update, context) is True
    db.update_chat_setting.assert_called_once_with(CID, "rules_text", "No spam.")


# ------------------------------- comando -------------------------------

@pytest.mark.asyncio
async def test_cmd_config_dm_un_grupo_abre_panel():
    db = _db()
    cfg = SimpleNamespace(admin_user_id=ADMIN)
    context = SimpleNamespace(bot_data={"cfg": cfg, "db": db}, user_data={})
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=ADMIN),
        effective_chat=SimpleNamespace(id=ADMIN, type="private"),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )
    await cp.cmd_config(update, context)
    kwargs = update.effective_message.reply_text.await_args.kwargs
    assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)


@pytest.mark.asyncio
async def test_cmd_config_dm_varios_grupos_muestra_selector():
    chats = [
        {"chat_id": -1, "title": "A", "am_admin": True},
        {"chat_id": -2, "title": "B", "am_admin": True},
    ]
    db = _db(chats=chats)
    db.get_pref.return_value = False  # sync OFF → selector por grupo
    cfg = SimpleNamespace(admin_user_id=ADMIN)
    context = SimpleNamespace(bot_data={"cfg": cfg, "db": db}, user_data={})
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=ADMIN),
        effective_chat=SimpleNamespace(id=ADMIN, type="private"),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )
    await cp.cmd_config(update, context)
    args = update.effective_message.reply_text.await_args
    assert "grupo" in args.args[0].lower()
    kb = args.kwargs["reply_markup"]
    assert len(kb.inline_keyboard) == 2


@pytest.mark.asyncio
async def test_cmd_config_sync_on_panel_unificado():
    """Con sync ON (default), en DM con varios grupos NO hay selector: panel unificado."""
    chats = [
        {"chat_id": -1, "title": "A", "am_admin": True},
        {"chat_id": -2, "title": "B", "am_admin": True},
    ]
    db = _db(chats=chats)  # get_pref None → sync ON
    cfg = SimpleNamespace(admin_user_id=ADMIN)
    context = SimpleNamespace(bot_data={"cfg": cfg, "db": db}, user_data={})
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=ADMIN),
        effective_chat=SimpleNamespace(id=ADMIN, type="private"),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )
    await cp.cmd_config(update, context)
    args = update.effective_message.reply_text.await_args
    assert "sincronizado" in args.args[0].lower()
    kb = args.kwargs["reply_markup"]
    assert len(kb.inline_keyboard) > 2  # panel completo, no selector de 2
    # primera fila = toggle de sincronización
    assert kb.inline_keyboard[0][0].callback_data.startswith("cfg:sync:")


@pytest.mark.asyncio
async def test_cmd_config_no_admin_no_hace_nada():
    db = _db()
    cfg = SimpleNamespace(admin_user_id=ADMIN)
    context = SimpleNamespace(bot_data={"cfg": cfg, "db": db}, user_data={})
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=555),
        effective_chat=SimpleNamespace(id=ADMIN, type="private"),
        effective_message=SimpleNamespace(reply_text=reply),
    )
    await cp.cmd_config(update, context)
    reply.assert_not_awaited()


# ================== bienvenida, botones, warns y top semanal ==================
# El panel principal no debe crecer: la bienvenida entera (interruptor, texto,
# botones y autoborrado) va en un submenú, y warns comparte fila con el top semanal.

def _flat(kb):
    return [b for row in kb.inline_keyboard for b in row]


def test_panel_agrupa_bienvenida_en_un_submenu():
    kb = cp.build_panel_keyboard(CID, _settings(welcome_enabled=1))
    flat = _flat(kb)
    menu = next(b for b in flat if b.callback_data == f"cfg:wsub:{CID}")
    assert "✅ ON" in menu.text                      # el estado se ve sin entrar
    # el texto de bienvenida ya no ocupa fila propia en el panel principal
    assert not any(b.callback_data == f"cfg:edit:w:{CID}" for b in flat)


def test_panel_warns_y_topweekly_comparten_fila():
    kb = cp.build_panel_keyboard(CID, _settings(topweekly_enabled=1))
    fila = next(r for r in kb.inline_keyboard
                if any(b.callback_data == f"cfg:warns:{CID}" for b in r))
    assert len(fila) == 2
    top = next(b for b in fila if b.callback_data == f"cfg:tog:topweekly_enabled:{CID}")
    assert "✅ ON" in top.text


def test_panel_no_crece_mas_de_una_fila():
    """Regresión de usabilidad: el panel principal no debe inflarse sin querer.
    Tope subido a 14 al añadir 'Rigor trabajo/dinero' (money_guard), en su propia
    fila por legibilidad en móvil. Si crece más, replantear agrupando en submenús."""
    kb = cp.build_panel_keyboard(CID, _settings())
    assert len(kb.inline_keyboard) <= 14


# ------------------------------ submenú bienvenida ------------------------------

def test_welcome_keyboard_refleja_estado_real():
    s = _settings(welcome_enabled=0, welcome_delete_after_s=3600)
    kb = cp.build_welcome_keyboard(CID, s, n_buttons=2)
    flat = _flat(kb)
    sw = next(b for b in flat if b.callback_data == f"cfg:tog:welcome_enabled:{CID}:w")
    assert "❌ OFF" in sw.text
    btns = next(b for b in flat if b.callback_data == f"cfg:wbtn:{CID}")
    assert "2" in btns.text
    ttl = next(b for b in flat if b.callback_data == f"cfg:wdel:{CID}")
    assert "1 h" in ttl.text


@pytest.mark.asyncio
async def test_toggle_welcome_desde_submenu_guarda_y_repinta_submenu():
    db = _db(_settings(welcome_enabled=1))
    update, context, q = _cbctx(db)
    q.data = f"cfg:tog:welcome_enabled:{CID}:w"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "welcome_enabled", 0)
    q.edit_message_text.assert_awaited_once()          # vuelve al submenú, no al panel
    q.edit_message_reply_markup.assert_not_awaited()


@pytest.mark.asyncio
async def test_toggle_sin_sufijo_de_vista_sigue_repintando_el_panel():
    """Retrocompatibilidad: los botones ya enviados a los chats no llevan 5º campo."""
    db = _db(_settings(cleanservice=1))
    update, context, q = _cbctx(db)
    q.data = f"cfg:tog:cleanservice:{CID}"
    await cp.on_callback(update, context)
    q.edit_message_reply_markup.assert_awaited_once()


# ------------------------------ autoborrado ------------------------------

def test_ttl_keyboard_marca_el_valor_actual():
    kb = cp.build_welcome_ttl_keyboard(CID, _settings(welcome_delete_after_s=300))
    sel = next(b for b in _flat(kb) if b.callback_data == f"cfg:wdset:300:{CID}")
    assert sel.text.startswith("✅")
    nunca = next(b for b in _flat(kb) if b.callback_data == f"cfg:wdset:0:{CID}")
    assert not nunca.text.startswith("✅")


@pytest.mark.asyncio
async def test_wdset_guarda_el_preset():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:wdset:3600:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "welcome_delete_after_s", 3600)


@pytest.mark.asyncio
async def test_wdset_valor_fuera_de_preset_rechazado():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:wdset:77:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()


@pytest.mark.asyncio
async def test_wdset_respeta_sync_on_y_escribe_en_todos():
    chats = [
        {"chat_id": -1, "title": "A", "am_admin": True},
        {"chat_id": -2, "title": "B", "am_admin": True},
    ]
    db = _db(chats=chats)  # get_pref None → sync ON
    update, context, q = _cbctx(db)
    q.data = "cfg:wdset:300:-1"
    await cp.on_callback(update, context)
    escritos = {c.args for c in db.update_chat_setting.call_args_list}
    assert (-1, "welcome_delete_after_s", 300) in escritos
    assert (-2, "welcome_delete_after_s", 300) in escritos


@pytest.mark.asyncio
async def test_wdset_con_sync_off_solo_toca_ese_grupo():
    chats = [
        {"chat_id": -1, "title": "A", "am_admin": True},
        {"chat_id": -2, "title": "B", "am_admin": True},
    ]
    db = _db(chats=chats)
    db.get_pref.return_value = False  # sync OFF
    update, context, q = _cbctx(db)
    q.data = "cfg:wdset:300:-1"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(-1, "welcome_delete_after_s", 300)


# ------------------------------ warns ------------------------------

def test_warns_keyboard_marca_limite_y_accion_actuales():
    kb = cp.build_warns_keyboard(CID, _settings(warns_limit=5, warns_action="mute"))
    flat = _flat(kb)
    assert next(b for b in flat if b.callback_data == f"cfg:wlim:5:{CID}").text.startswith("✅")
    assert not next(b for b in flat if b.callback_data == f"cfg:wlim:3:{CID}").text.startswith("✅")
    assert next(b for b in flat if b.callback_data == f"cfg:wact:mute:{CID}").text.startswith("✅")
    assert not next(b for b in flat if b.callback_data == f"cfg:wact:ban:{CID}").text.startswith("✅")


@pytest.mark.asyncio
async def test_wlim_guarda_el_limite():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:wlim:10:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "warns_limit", 10)


@pytest.mark.asyncio
async def test_wact_guarda_la_accion():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:wact:kick:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "warns_action", "kick")


@pytest.mark.asyncio
async def test_wact_accion_desconocida_rechazada():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:wact:borrar_grupo:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()


@pytest.mark.asyncio
async def test_wlim_respeta_sync_on():
    chats = [
        {"chat_id": -1, "title": "A", "am_admin": True},
        {"chat_id": -2, "title": "B", "am_admin": True},
    ]
    db = _db(chats=chats)
    update, context, q = _cbctx(db)
    q.data = "cfg:wlim:5:-1"
    await cp.on_callback(update, context)
    escritos = {c.args for c in db.update_chat_setting.call_args_list}
    assert (-1, "warns_limit", 5) in escritos and (-2, "warns_limit", 5) in escritos


# ------------------------------ top semanal ------------------------------

@pytest.mark.asyncio
async def test_topweekly_toggle_invierte_el_valor():
    db = _db(_settings(topweekly_enabled=0))
    update, context, q = _cbctx(db)
    q.data = f"cfg:tog:topweekly_enabled:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_called_once_with(CID, "topweekly_enabled", 1)


# ==================== URLs de los botones de bienvenida ====================
# Lo delicado: Telegram RECHAZA el mensaje entero si una URL de botón no le vale,
# y el grupo se queda sin bienvenida sin que nadie entienda por qué.

@pytest.mark.parametrize("crudo,esperado", [
    ("https://t.me/grupo", "https://t.me/grupo"),
    ("http://ejemplo.com/normas", "http://ejemplo.com/normas"),
    ("t.me/grupo/12", "https://t.me/grupo/12"),           # sin esquema → https
    ("ejemplo.com", "https://ejemplo.com"),
    ("  https://t.me/x  ", "https://t.me/x"),             # se recortan espacios
])
def test_url_valida_se_normaliza(crudo, esperado):
    url, err = cp.validate_button_url(crudo)
    assert err is None and url == esperado


@pytest.mark.parametrize("crudo", [
    "",                       # vacía
    "javascript:alert(1)",    # esquema peligroso
    "tg://resolve?domain=x",  # esquema que no es http/https
    "mailto:hola@ejemplo.com",
    "ftp://ejemplo.com",
    "https://ejemplo .com",   # espacios
    "https://localhost",      # host sin punto
    "solotexto",
    "https://",
    "https://" + "a" * 600,   # demasiado larga
])
def test_url_invalida_se_rechaza(crudo):
    url, err = cp.validate_button_url(crudo)
    assert url is None and err and err.startswith("cfg.wb.err_")


def test_parse_button_spec_completo():
    text, url, same, err = cp.parse_button_spec("Normas | t.me/grupo/1 same")
    assert err is None and text == "Normas" and url == "https://t.me/grupo/1" and same is True


def test_parse_button_spec_sin_barra():
    assert cp.parse_button_spec("Normas https://t.me/x")[3] == "cfg.wb.err_pipe"


def test_parse_button_spec_sin_texto():
    assert cp.parse_button_spec(" | https://t.me/x")[3] == "cfg.wb.err_text"


# ------------------- alta de botón por captura de texto -------------------

def _capture_ctx(db, chat_id=CID):
    context = SimpleNamespace(
        bot_data={"db": db},
        user_data={"cfg_await": {"field": "welcome_button", "chat_id": chat_id}},
    )
    msg = SimpleNamespace(text=None, caption=None, reply_text=AsyncMock())
    update = SimpleNamespace(effective_message=msg)
    return update, context, msg


@pytest.mark.asyncio
async def test_capture_boton_valido_se_guarda_normalizado():
    db = _db()
    update, context, msg = _capture_ctx(db)
    msg.text = "Normas | t.me/grupo/1"
    assert await cp.handle_capture(update, context) is True
    db.add_welcome_button.assert_called_once()
    args, kwargs = db.add_welcome_button.call_args
    assert args[0] == CID and args[1] == "Normas" and args[2] == "https://t.me/grupo/1"
    assert kwargs["same_row"] is False
    assert "cfg_await" not in context.user_data          # un solo uso


@pytest.mark.asyncio
async def test_capture_boton_url_invalida_no_se_guarda():
    """Lo importante: NO llega a la BD, así el grupo nunca se queda sin bienvenida."""
    db = _db()
    update, context, msg = _capture_ctx(db)
    msg.text = "Pincha aquí | javascript:alert(1)"
    assert await cp.handle_capture(update, context) is True
    db.add_welcome_button.assert_not_called()
    db.update_chat_setting.assert_not_called()
    aviso = msg.reply_text.await_args.args[0]
    assert "http" in aviso and "bienvenida" in aviso.lower()   # explica el porqué


@pytest.mark.asyncio
async def test_capture_boton_sin_barra_avisa_del_formato():
    db = _db()
    update, context, msg = _capture_ctx(db)
    msg.text = "Normas https://t.me/x"
    assert await cp.handle_capture(update, context) is True
    db.add_welcome_button.assert_not_called()
    assert "|" in msg.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_capture_boton_respeta_sync_on():
    chats = [
        {"chat_id": -1, "title": "A", "am_admin": True},
        {"chat_id": -2, "title": "B", "am_admin": True},
    ]
    db = _db(chats=chats)
    update, context, msg = _capture_ctx(db, chat_id=-1)
    msg.text = "Normas | https://t.me/grupo/1"
    assert await cp.handle_capture(update, context) is True
    destinos = {c.args[0] for c in db.add_welcome_button.call_args_list}
    assert destinos == {-1, -2}


@pytest.mark.asyncio
async def test_wbadd_arma_la_captura():
    db = _db()
    update, context, q = _cbctx(db)
    q.data = f"cfg:wbadd:{CID}"
    await cp.on_callback(update, context)
    assert context.user_data["cfg_await"] == {"field": "welcome_button", "chat_id": CID}


# ------------------- borrado de botones -------------------

@pytest.mark.asyncio
async def test_wbdel_con_sync_on_borra_el_gemelo_de_cada_grupo():
    """Los ids son por chat: con sync ON el gemelo se localiza por texto+URL."""
    chats = [
        {"chat_id": -1, "title": "A", "am_admin": True},
        {"chat_id": -2, "title": "B", "am_admin": True},
    ]
    db = _db(chats=chats)
    db.get_welcome_button.return_value = {"text": "Normas", "url": "https://t.me/g/1"}
    update, context, q = _cbctx(db)
    q.data = "cfg:wbdel:7:-1"
    await cp.on_callback(update, context)
    borrados = {c.args for c in db.delete_welcome_buttons_like.call_args_list}
    assert (-1, "Normas", "https://t.me/g/1") in borrados
    assert (-2, "Normas", "https://t.me/g/1") in borrados


@pytest.mark.asyncio
async def test_wbdel_con_sync_off_borra_solo_por_id():
    db = _db()
    db.get_pref.return_value = False  # sync OFF
    db.get_welcome_button.return_value = {"text": "Normas", "url": "https://t.me/g/1"}
    update, context, q = _cbctx(db)
    q.data = f"cfg:wbdel:7:{CID}"
    await cp.on_callback(update, context)
    db.delete_welcome_button.assert_called_once_with(7)
    db.delete_welcome_buttons_like.assert_not_called()


@pytest.mark.asyncio
async def test_wbclr_quita_todos_en_los_grupos_sincronizados():
    chats = [
        {"chat_id": -1, "title": "A", "am_admin": True},
        {"chat_id": -2, "title": "B", "am_admin": True},
    ]
    db = _db(chats=chats)
    update, context, q = _cbctx(db)
    q.data = "cfg:wbclr:-1"
    await cp.on_callback(update, context)
    assert {c.args[0] for c in db.clear_welcome_buttons.call_args_list} == {-1, -2}


def test_welcome_buttons_keyboard_lista_y_permite_quitar():
    buttons = [{"id": 3, "text": "Normas", "url": "https://t.me/g/1"}]
    kb = cp.build_welcome_buttons_keyboard(CID, buttons)
    flat = _flat(kb)
    assert any(b.callback_data == f"cfg:wbdel:3:{CID}" for b in flat)
    assert any(b.callback_data == f"cfg:wbadd:{CID}" for b in flat)
    assert any(b.callback_data == f"cfg:wbclr:{CID}" for b in flat)


def test_welcome_buttons_keyboard_sin_botones_no_ofrece_quitar_todos():
    kb = cp.build_welcome_buttons_keyboard(CID, [])
    flat = _flat(kb)
    assert not any(b.callback_data == f"cfg:wbclr:{CID}" for b in flat)
    assert any(b.callback_data == f"cfg:wbadd:{CID}" for b in flat)
