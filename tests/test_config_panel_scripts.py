"""Panel de alfabetos permitidos: quién puede escribir sin que el bot lo marque.

Lo que se protege aquí, por orden de gravedad si se rompiera:

1. Que la lista NUNCA se quede vacía. Sin ningún alfabeto permitido, `non_allowed_ratio`
   da «no permitido» para CUALQUIER letra y el bot marcaría el grupo entero.
2. Que la pantalla enseñe lo que el bot aplica DE VERDAD, incluido lo heredado del
   .env: si enseñara la columna a pelo, un grupo que permite cirílico por .env vería
   todo apagado y lo «activaría» creyendo que estaba off.
3. Que la pista de alfabetos cuente sobre mensajes reales del grupo y señale los que
   no están permitidos, que son justo los que van a dar falsos positivos.
4. Que el callback quepa en los 64 bytes con un chat_id de los largos.
5. Que solo el admin del bot llegue a nada de esto.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import config_panel as cp
from src.detectors import unicode_script
from src.locales import STRINGS

ADMIN = 999
CID = -1001234567890          # un id de supergrupo real, de los largos
OTRO = -1009876543210


def _cfg(allowed=("latin",)):
    return SimpleNamespace(admin_user_id=ADMIN, allowed_scripts=list(allowed))


def _cbctx(db, cfg=None, user_id=ADMIN):
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
        bot_data={"cfg": cfg if cfg is not None else _cfg(), "db": db},
        user_data={},
        bot=SimpleNamespace(send_message=AsyncMock()),
    )
    return update, context, q


def _datos(kb) -> list[str]:
    return [b.callback_data for row in kb.inline_keyboard for b in row]


def _textos(kb) -> list[str]:
    return [b.text for row in kb.inline_keyboard for b in row]


def _mensajes(db, textos: list[str], chat_id: int = CID) -> None:
    """Conversación real del grupo, que es lo que mira la pista de alfabetos."""
    for i, txt in enumerate(textos, start=1):
        db.record_join(chat_id, 1000 + i, f"user{i}")
        db.update_last_message(chat_id, 1000 + i, i, txt)


# ------------------------------- opciones y etiquetas -------------------------------

def test_las_opciones_salen_del_detector_no_de_una_lista_a_mano():
    """Si el detector aprende un alfabeto nuevo, el panel debe ofrecerlo solo."""
    del_detector = {name for _, _, name in unicode_script._SCRIPT_RANGES}
    assert del_detector <= set(cp._SCRIPT_CHOICES)
    # ...y "other", que es como `script_of()` etiqueta lo que no tiene rango propio
    # (tailandés, armenio...). Sin él ese grupo no podría permitir su alfabeto.
    assert "other" in cp._SCRIPT_CHOICES
    assert cp._script_label("other") != "cfg.sc.name.other"


def test_cada_alfabeto_tiene_nombre_en_los_dos_idiomas():
    """Sin esto el botón enseñaría la clave cruda ('cfg.sc.name.cyrillic')."""
    faltan = [
        f"{code}:{name}"
        for name in cp._SCRIPT_CHOICES
        for code in ("es", "en")
        if f"cfg.sc.name.{name}" not in STRINGS[code]
    ]
    assert not faltan, f"alfabetos sin nombre traducido: {faltan}"


def test_alfabeto_sin_traducir_no_enseña_la_clave():
    """Doble guarda de `t()`: antes que «cfg.sc.name.thai», el nombre técnico."""
    assert cp._script_label("thai") == "Thai"


def test_orden_estable_y_sin_duplicados():
    assert cp._sorted_scripts(["han", "latin", "latin"]) == ["latin", "han"]
    # lo que el detector no reconoce no se pierde: va al final
    assert cp._sorted_scripts(["thai", "latin"]) == ["latin", "thai"]


# --------------------------------- estado en pantalla ---------------------------------

def test_el_panel_principal_ofrece_los_alfabetos(tmp_db):
    tmp_db.ensure_chat_settings(CID)
    kb = cp.build_panel_keyboard(CID, tmp_db.get_chat_settings(CID))
    assert f"cfg:sc:{CID}" in _datos(kb)


def test_estado_heredado_del_env_cuando_la_columna_es_null(tmp_db):
    """El caso que más engaña: la columna está a NULL y manda el .env."""
    tmp_db.ensure_chat_settings(CID)
    assert tmp_db.get_chat_settings(CID)["allowed_scripts"] is None
    activos = cp._allowed_scripts(tmp_db, _cfg(["latin", "cyrillic"]), CID)
    assert activos == ["latin", "cyrillic"]
    assert cp._scripts_inherited(tmp_db.get_chat_settings(CID)) is True


def test_estado_propio_manda_sobre_el_env(tmp_db):
    tmp_db.ensure_chat_settings(CID)
    tmp_db.update_chat_setting(CID, "allowed_scripts", "latin,arabic")
    assert cp._allowed_scripts(tmp_db, _cfg(["latin"]), CID) == ["latin", "arabic"]
    assert cp._scripts_inherited(tmp_db.get_chat_settings(CID)) is False


@pytest.mark.asyncio
async def test_el_submenu_marca_los_activos_incluidos_los_heredados(tmp_db):
    tmp_db.ensure_chat_settings(CID)
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), _cfg(["latin", "cyrillic"]))
    q.data = f"cfg:sc:{CID}"
    await cp.on_callback(update, context)
    kb = q.edit_message_text.await_args.kwargs["reply_markup"]
    marcados = {tx for tx in _textos(kb) if tx.startswith("✅")}
    assert marcados == {"✅ Latino", "✅ Cirílico"}
    assert "▫️ Árabe" in _textos(kb)
    texto = q.edit_message_text.await_args.args[0]
    assert "ALLOWED_SCRIPTS" in texto           # avisa de que viene del .env
    assert "Latino, Cirílico" in texto


@pytest.mark.asyncio
async def test_un_alfabeto_permitido_por_env_que_el_detector_no_conoce_es_quitable(tmp_db):
    """`ALLOWED_SCRIPTS=latin,thai` no puede dejar 'thai' permitido y sin botón."""
    tmp_db.ensure_chat_settings(CID)
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), _cfg(["latin", "thai"]))
    q.data = f"cfg:sc:{CID}"
    await cp.on_callback(update, context)
    kb = q.edit_message_text.await_args.kwargs["reply_markup"]
    assert f"cfg:scset:thai:{CID}" in _datos(kb)
    assert "✅ Thai" in _textos(kb)


# ------------------------- la guarda del último alfabeto -------------------------

@pytest.mark.asyncio
async def test_quitar_el_ultimo_alfabeto_se_rechaza_con_aviso(tmp_db):
    """Lo más grave del submenú: sin ninguno permitido se marca el grupo entero."""
    tmp_db.ensure_chat_settings(CID)
    tmp_db.update_chat_setting(CID, "allowed_scripts", "latin")
    db = MagicMock(wraps=tmp_db)
    update, context, q = _cbctx(db, _cfg(["latin"]))
    q.data = f"cfg:scset:latin:{CID}"
    await cp.on_callback(update, context)

    # avisa con alerta (no un toast que se pierde) y NO toca la BD
    q.answer.assert_awaited_once()
    assert q.answer.await_args.kwargs.get("show_alert") is True
    assert "último" in q.answer.await_args.args[0]
    db.update_chat_setting.assert_not_called()
    assert tmp_db.get_chat_settings(CID)["allowed_scripts"] == "latin"


@pytest.mark.asyncio
async def test_la_guarda_tambien_vale_con_el_ultimo_heredado_del_env(tmp_db):
    """Con la columna a NULL el único activo es el del .env: tampoco se puede quitar."""
    tmp_db.ensure_chat_settings(CID)
    db = MagicMock(wraps=tmp_db)
    update, context, q = _cbctx(db, _cfg(["latin"]))
    q.data = f"cfg:scset:latin:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()
    assert tmp_db.get_chat_settings(CID)["allowed_scripts"] is None


@pytest.mark.asyncio
async def test_quitar_uno_de_dos_si_se_guarda(tmp_db):
    tmp_db.ensure_chat_settings(CID)
    tmp_db.update_chat_setting(CID, "allowed_scripts", "latin,cyrillic")
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), _cfg(["latin"]))
    q.data = f"cfg:scset:cyrillic:{CID}"
    await cp.on_callback(update, context)
    assert tmp_db.get_chat_settings(CID)["allowed_scripts"] == "latin"


@pytest.mark.asyncio
async def test_activar_uno_nuevo_guarda_el_csv_ordenado(tmp_db):
    """Partiendo de la herencia del .env, activar suma sin perder lo heredado."""
    tmp_db.ensure_chat_settings(CID)
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), _cfg(["latin"]))
    q.data = f"cfg:scset:arabic:{CID}"
    await cp.on_callback(update, context)
    assert tmp_db.get_chat_settings(CID)["allowed_scripts"] == "latin,arabic"


@pytest.mark.asyncio
async def test_un_alfabeto_inventado_en_el_callback_no_se_guarda(tmp_db):
    tmp_db.ensure_chat_settings(CID)
    db = MagicMock(wraps=tmp_db)
    update, context, q = _cbctx(db, _cfg(["latin"]))
    q.data = f"cfg:scset:klingon:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()


@pytest.mark.asyncio
async def test_solo_el_admin_del_bot(tmp_db):
    db = MagicMock(wraps=tmp_db)
    update, context, q = _cbctx(db, _cfg(["latin"]), user_id=ADMIN + 1)
    q.data = f"cfg:scset:arabic:{CID}"
    await cp.on_callback(update, context)
    db.update_chat_setting.assert_not_called()
    q.edit_message_text.assert_not_awaited()


# ---------------------------------- sincronización ----------------------------------

@pytest.mark.asyncio
async def test_con_sync_on_el_cambio_va_a_todos_los_grupos(tmp_db):
    for cid in (CID, OTRO):
        tmp_db.upsert_bot_chat(cid, f"Grupo {cid}", "supergroup", True, True, True)
        tmp_db.ensure_chat_settings(cid)
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), _cfg(["latin"]))
    q.data = f"cfg:scset:cyrillic:{CID}"
    await cp.on_callback(update, context)
    assert tmp_db.get_chat_settings(CID)["allowed_scripts"] == "latin,cyrillic"
    assert tmp_db.get_chat_settings(OTRO)["allowed_scripts"] == "latin,cyrillic"
    assert "2" in q.answer.await_args.args[0]          # el toast dice a cuántos


@pytest.mark.asyncio
async def test_con_sync_off_solo_cambia_ese_grupo(tmp_db):
    for cid in (CID, OTRO):
        tmp_db.upsert_bot_chat(cid, f"Grupo {cid}", "supergroup", True, True, True)
        tmp_db.ensure_chat_settings(cid)
    tmp_db.set_pref("config_sync", False)
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), _cfg(["latin"]))
    q.data = f"cfg:scset:cyrillic:{CID}"
    await cp.on_callback(update, context)
    assert tmp_db.get_chat_settings(CID)["allowed_scripts"] == "latin,cyrillic"
    assert tmp_db.get_chat_settings(OTRO)["allowed_scripts"] is None


# ------------------------------- límite de 64 bytes -------------------------------

def test_el_callback_cabe_en_64_bytes_con_el_chat_id_mas_largo():
    """Telegram corta a 64 BYTES: el peor caso es el alfabeto de nombre más largo."""
    peor_chat = -1009999999999999          # más largo que los ids de hoy
    for kb in (cp.build_scripts_keyboard(peor_chat, ["latin", "devanagari"]),
               cp.build_scripts_keyboard(CID, list(cp._SCRIPT_CHOICES))):
        for data in _datos(kb):
            assert len(data.encode("utf-8")) <= 64, data


# ------------------------- la pista: qué escribe el grupo -------------------------

def test_la_pista_cuenta_los_alfabetos_de_los_mensajes_reales(tmp_db):
    _mensajes(tmp_db, [
        "hola buenas, alguien sabe si llueve",
        "acabo de actualizar a Windows 11",
        "привет всем, как дела",
        "спасибо большое",
        "здравствуйте",
    ])
    vistos, scanned = cp.scripts_seen(tmp_db, CID)
    assert scanned == 5
    assert vistos == {"latin": 2, "cyrillic": 3}


def test_la_pista_ignora_emojis_cifras_y_signos(tmp_db):
    _mensajes(tmp_db, ["👍👍👍", "2026 !!! ???", "hola"])
    vistos, scanned = cp.scripts_seen(tmp_db, CID)
    assert scanned == 3            # se examinan los tres
    assert vistos == {"latin": 1}  # pero solo uno tiene letras


def test_una_palabra_suelta_no_convierte_el_grupo_en_bilingue(tmp_db):
    """Anti falso positivo de la propia pista: una palabra suelta no es un alfabeto
    del grupo. Aquí el cirílico son 6 letras de 60: por debajo del mínimo."""
    _mensajes(tmp_db, [
        "muchas gracias por la ayuda con el ordenador, ya me funciona привет",
        "gracias, ya me funciona el driver de la grafica sin ningun problema",
    ])
    vistos, _ = cp.scripts_seen(tmp_db, CID)
    assert vistos == {"latin": 2}
    # una mezcla de verdad sí cuenta las dos
    _mensajes(tmp_db, ["привет, tengo Windows"], chat_id=OTRO)
    otros, _ = cp.scripts_seen(tmp_db, OTRO)
    assert otros == {"latin": 1, "cyrillic": 1}


def test_la_pista_solo_mira_ese_grupo(tmp_db):
    _mensajes(tmp_db, ["hola que tal"], chat_id=CID)
    _mensajes(tmp_db, ["привет всем"], chat_id=OTRO)
    assert cp.scripts_seen(tmp_db, CID)[0] == {"latin": 1}
    assert cp.scripts_seen(tmp_db, OTRO)[0] == {"cyrillic": 1}


def test_la_pista_esta_acotada(tmp_db):
    _mensajes(tmp_db, ["hola"] * 30)
    _, scanned = cp.scripts_seen(tmp_db, CID, limit=10)
    assert scanned == 10


def test_la_pista_no_tumba_la_pantalla_si_la_consulta_falla():
    db = MagicMock()
    db.recent_message_texts.side_effect = RuntimeError("BD ocupada")
    assert cp.scripts_seen(db, CID) == ({}, 0)


@pytest.mark.asyncio
async def test_la_pantalla_destaca_el_alfabeto_que_el_grupo_usa_y_no_esta_permitido(tmp_db):
    """El caso que da valor a la pista: cirílico en el grupo, solo latino permitido."""
    tmp_db.ensure_chat_settings(CID)
    _mensajes(tmp_db, ["привет всем", "спасибо", "hola buenas"])
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), _cfg(["latin"]))
    q.data = f"cfg:sc:{CID}"
    await cp.on_callback(update, context)
    texto = q.edit_message_text.await_args.args[0]
    assert "Cirílico: 2 ⛔" in texto            # señalado uno a uno
    assert "<b>Cirílico</b>" in texto          # y en el aviso de arriba
    assert "Latino: 1 ✅" in texto


@pytest.mark.asyncio
async def test_sin_mensajes_guardados_lo_dice_en_vez_de_callar(tmp_db):
    tmp_db.ensure_chat_settings(CID)
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), _cfg(["latin"]))
    q.data = f"cfg:sc:{CID}"
    await cp.on_callback(update, context)
    texto = q.edit_message_text.await_args.args[0]
    assert "no puedo decirte" in texto.lower()


def test_el_texto_escapa_el_titulo_del_grupo(tmp_db):
    """El título lo escribe un humano: sin escapar, un `<` tumba el mensaje entero."""
    tmp_db.upsert_bot_chat(CID, "Grupo <b>raro</b> & cia", "supergroup", True, True, True)
    tmp_db.set_pref("config_sync", False)
    texto = cp._scripts_text(tmp_db, CID, ["latin"], True)
    assert "&lt;b&gt;raro&lt;/b&gt; &amp; cia" in texto
    assert "<b>raro</b>" not in texto
