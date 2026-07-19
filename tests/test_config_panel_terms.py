"""Panel de palabras bloqueadas: la vista previa es obligatoria y nada se guarda solo.

Lo que se protege aquí, por orden de gravedad si se rompiera:

1. Que NO se pueda guardar un término sin haber visto antes lo que cazaría. Es la
   única barrera entre «se me ocurre bloquear "oferta"» y banear a medio grupo.
2. Que un botón ya enviado nunca borre el término equivocado (los identificadores
   viajan por callback y la lista cambia bajo los pies).
3. Que un término escrito por un humano (con `<`, con acentos, largo) no reviente
   ni el mensaje HTML ni el límite de 64 bytes del callback_data.
4. Que solo el admin del bot llegue a nada de esto.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import config_panel as cp
from src import custom_terms, wordlists
from src.locales import STRINGS

ADMIN = 999
CID = -1001234567890          # un id de supergrupo real, de los largos
LISTA = "commercial_work.txt"
IDX = custom_terms.MANAGEABLE_LISTS.index(LISTA)


@pytest.fixture(autouse=True)
def _blacklist_aislada(tmp_path, monkeypatch):
    """Listas propias en un directorio de usar y tirar: no tocamos las del repo."""
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    wordlists.clear_cache()
    yield
    wordlists.clear_cache()


def _cfg():
    return SimpleNamespace(admin_user_id=ADMIN, public_quip_enabled=True)


def _cbctx(db, user_id=ADMIN, user_data=None):
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
        bot_data={"cfg": _cfg(), "db": db},
        user_data=user_data if user_data is not None else {},
        bot=SimpleNamespace(send_message=AsyncMock()),
    )
    return update, context, q


def _capctx(db, user_data, texto: str):
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_message=SimpleNamespace(text=texto, caption=None, reply_text=reply),
    )
    context = SimpleNamespace(bot_data={"cfg": _cfg(), "db": db}, user_data=user_data)
    return update, context, reply


def _datos(kb) -> list[str]:
    return [b.callback_data for row in kb.inline_keyboard for b in row]


def _mensajes(db, textos: list[str], chat_id: int = CID) -> None:
    """Mete conversación real del grupo, que es lo que mira la vista previa."""
    for i, txt in enumerate(textos, start=1):
        db.record_join(chat_id, 1000 + i, f"user{i}")
        db.update_last_message(chat_id, 1000 + i, i, txt)


# ------------------------------ pintado del panel ------------------------------

def test_el_panel_principal_ofrece_las_palabras_bloqueadas(tmp_db):
    tmp_db.ensure_chat_settings(CID)
    kb = cp.build_panel_keyboard(CID, tmp_db.get_chat_settings(CID))
    assert f"cfg:ct:{CID}" in _datos(kb)


@pytest.mark.asyncio
async def test_la_pantalla_lista_todas_las_listas_gestionables(tmp_db):
    update, context, q = _cbctx(MagicMock(wraps=tmp_db))
    q.data = f"cfg:ct:{CID}"
    await cp.on_callback(update, context)
    datos = _datos(q.edit_message_text.await_args.kwargs["reply_markup"])
    for i in range(len(custom_terms.MANAGEABLE_LISTS)):
        assert f"cfg:ctl:{i}:{CID}" in datos


@pytest.mark.asyncio
async def test_la_lista_pinta_sus_terminos_y_el_boton_de_anadir(tmp_db):
    custom_terms.add_term(LISTA, "curriculum vitae")
    update, context, q = _cbctx(MagicMock(wraps=tmp_db))
    q.data = f"cfg:ctl:{IDX}:{CID}"
    await cp.on_callback(update, context)
    texto = q.edit_message_text.await_args.args[0]
    kb = q.edit_message_text.await_args.kwargs["reply_markup"]
    assert "curriculum vitae" in texto
    assert f"cfg:ctadd:{IDX}:{CID}" in _datos(kb)


def test_cada_lista_gestionable_tiene_nombre_en_los_dos_idiomas():
    """Sin esto el panel enseñaría la clave cruda ('cfg.ct.name.commercial_work')."""
    faltan = [
        f"{code}:{fn}"
        for fn in custom_terms.MANAGEABLE_LISTS
        for code in ("es", "en")
        if f"cfg.ct.name.{fn.removesuffix('.txt')}" not in STRINGS[code]
    ]
    assert not faltan, f"listas sin nombre traducido: {faltan}"


def test_cada_codigo_de_error_tiene_texto_en_los_dos_idiomas():
    faltan = [
        f"{code}:{clave}"
        for clave in [*cp._TERM_ERR_KEYS.values(), "cfg.ct.err.generico"]
        for code in ("es", "en")
        if clave not in STRINGS[code]
    ]
    assert not faltan, f"errores sin traducir: {faltan}"


# --------------------- el alta pasa SIEMPRE por la vista previa ---------------------

@pytest.mark.asyncio
async def test_escribir_el_termino_no_lo_guarda_todavia(tmp_db):
    """El fallo grave a evitar: que el término entre en el archivo nada más escribirlo."""
    _mensajes(tmp_db, ["hola buenas", "alguien sabe si llueve"])
    user_data = {"cfg_await": {"field": "custom_term", "chat_id": CID},
                 "cfg_term": {"list": LISTA, "chat_id": CID}}
    update, context, reply = _capctx(tmp_db, user_data, "busco personal")

    assert await cp.handle_capture(update, context) is True

    assert custom_terms.list_terms(LISTA) == []          # NADA guardado
    texto = reply.await_args.args[0]
    assert "busco personal" in texto
    kb = reply.await_args.kwargs["reply_markup"]
    assert f"cfg:ctok:{IDX}:{CID}" in _datos(kb)          # solo se ofrece confirmar


@pytest.mark.asyncio
async def test_solo_al_confirmar_se_guarda(tmp_db):
    user_data = {"cfg_term": {"list": LISTA, "term": "busco personal", "chat_id": CID}}
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), user_data=user_data)
    q.data = f"cfg:ctok:{IDX}:{CID}"
    await cp.on_callback(update, context)
    assert custom_terms.list_terms(LISTA) == ["busco personal"]
    assert "cfg_term" not in context.user_data       # no se puede confirmar dos veces


@pytest.mark.asyncio
async def test_confirmar_sin_vista_previa_previa_no_guarda_nada(tmp_db):
    """Un `ctok` suelto (mensaje viejo, bot reiniciado) no debe inventarse un término."""
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), user_data={})
    q.data = f"cfg:ctok:{IDX}:{CID}"
    await cp.on_callback(update, context)
    assert custom_terms.list_terms(LISTA) == []


@pytest.mark.asyncio
async def test_confirmar_en_otra_lista_distinta_no_cuela(tmp_db):
    """La confirmación tiene que casar con la lista que se previsualizó."""
    otra = custom_terms.MANAGEABLE_LISTS.index("commercial_urgency.txt")
    user_data = {"cfg_term": {"list": LISTA, "term": "busco personal", "chat_id": CID}}
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), user_data=user_data)
    q.data = f"cfg:ctok:{otra}:{CID}"
    await cp.on_callback(update, context)
    assert custom_terms.list_terms("commercial_urgency.txt") == []
    assert custom_terms.list_terms(LISTA) == []


# ------------------------------ avisos de la vista previa ------------------------------

@pytest.mark.asyncio
async def test_un_termino_que_arrasa_avisa_a_gritos_y_cambia_el_boton(tmp_db):
    """«hola» cazaría media conversación: el aviso tiene que ser imposible de pasar
    por alto y el botón no puede poner «Añadir» a secas."""
    _mensajes(tmp_db, [f"hola que tal {i}" for i in range(6)])
    user_data = {"cfg_await": {"field": "custom_term", "chat_id": CID},
                 "cfg_term": {"list": LISTA, "chat_id": CID}}
    update, context, reply = _capctx(tmp_db, user_data, "hola que tal")

    await cp.handle_capture(update, context)

    texto = reply.await_args.args[0]
    assert "🚨" in texto
    boton = reply.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert boton.text == cp.t("cfg.ct.b.add_anyway")


@pytest.mark.asyncio
async def test_coincidir_con_un_mensaje_marcado_legitimo_es_el_aviso_mas_fuerte(tmp_db):
    """Un hit en /legal es un falso positivo que confirmó el propio admin."""
    tmp_db.add_sample("busco personal para mi tienda", "h1", "ham", ADMIN, CID, 1)
    user_data = {"cfg_await": {"field": "custom_term", "chat_id": CID},
                 "cfg_term": {"list": LISTA, "chat_id": CID}}
    update, context, reply = _capctx(tmp_db, user_data, "busco personal")

    await cp.handle_capture(update, context)

    texto = reply.await_args.args[0]
    assert "🚨" in texto
    assert "/legal" in texto


@pytest.mark.asyncio
async def test_un_termino_limpio_se_ofrece_con_el_boton_normal(tmp_db):
    _mensajes(tmp_db, ["hola buenas", "alguien sabe si llueve"])
    user_data = {"cfg_await": {"field": "custom_term", "chat_id": CID},
                 "cfg_term": {"list": LISTA, "chat_id": CID}}
    update, context, reply = _capctx(tmp_db, user_data, "contrato indefinido")

    await cp.handle_capture(update, context)

    boton = reply.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert boton.text == cp.t("cfg.ct.b.add_ok")


@pytest.mark.asyncio
async def test_los_ejemplos_se_recortan_y_no_dicen_quien_los_escribio(tmp_db):
    largo = "necesito personal urgente " + "y mucho texto de relleno " * 20
    _mensajes(tmp_db, [largo])
    user_data = {"cfg_await": {"field": "custom_term", "chat_id": CID},
                 "cfg_term": {"list": LISTA, "chat_id": CID}}
    update, context, reply = _capctx(tmp_db, user_data, "necesito personal")

    await cp.handle_capture(update, context)

    texto = reply.await_args.args[0]
    assert "…" in texto                    # se cortó
    assert "user1" not in texto            # sin autor
    assert len(largo) > len(texto)         # no se pegó el mensaje entero


# ------------------------------ términos rechazados ------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("termino,pista", [
    ("ya", "4"),                     # más corto que MIN_TERM_LEN → dice el mínimo
    ("!!!!!", "signos"),             # sin letras ni números
    ("-oferta-", "letra"),           # bordes de símbolo en una lista con \b
])
async def test_un_termino_rechazado_no_se_guarda_y_explica_por_que(tmp_db, termino, pista):
    user_data = {"cfg_await": {"field": "custom_term", "chat_id": CID},
                 "cfg_term": {"list": LISTA, "chat_id": CID}}
    update, context, reply = _capctx(tmp_db, user_data, termino)

    await cp.handle_capture(update, context)

    assert custom_terms.list_terms(LISTA) == []
    texto = reply.await_args.args[0]
    assert pista in texto
    assert texto != cp.t("cfg.ct.err.generico")           # no es el error de relleno
    assert "reply_markup" not in reply.await_args.kwargs  # sin botón de confirmar
    assert "cfg_term" not in context.user_data            # el flujo se cierra


@pytest.mark.asyncio
async def test_un_duplicado_se_explica_como_duplicado(tmp_db):
    custom_terms.add_term(LISTA, "busco personal")
    user_data = {"cfg_await": {"field": "custom_term", "chat_id": CID},
                 "cfg_term": {"list": LISTA, "chat_id": CID}}
    update, context, reply = _capctx(tmp_db, user_data, "Busco Personal")

    await cp.handle_capture(update, context)

    assert custom_terms.list_terms(LISTA) == ["busco personal"]   # sigue habiendo uno
    assert reply.await_args.args[0] == cp.t("cfg.ct.err.duplicado")


def test_el_texto_de_error_lleva_el_numero_concreto():
    corto = cp._term_error_text(custom_terms.validate_term(LISTA, "ya"))
    assert str(custom_terms.MIN_TERM_LEN) in corto


# ---------------------------------- quitar ----------------------------------

@pytest.mark.asyncio
async def test_quitar_pide_confirmacion_y_solo_entonces_borra(tmp_db):
    custom_terms.add_term(LISTA, "busco personal")
    h = cp._term_hash("busco personal")

    update, context, q = _cbctx(MagicMock(wraps=tmp_db))
    q.data = f"cfg:ctdel:{IDX}:{h}:{CID}"
    await cp.on_callback(update, context)
    assert custom_terms.list_terms(LISTA) == ["busco personal"]   # aún no
    assert f"cfg:ctdelok:{IDX}:{h}:{CID}" in _datos(
        q.edit_message_text.await_args.kwargs["reply_markup"])

    q.data = f"cfg:ctdelok:{IDX}:{h}:{CID}"
    await cp.on_callback(update, context)
    assert custom_terms.list_terms(LISTA) == []


@pytest.mark.asyncio
async def test_un_boton_viejo_no_borra_el_termino_equivocado(tmp_db):
    """El motivo de identificar por hash y no por posición: si el término ya no está,
    el botón antiguo no debe llevarse por delante al que ocupa ahora su sitio."""
    custom_terms.add_term(LISTA, "busco personal")
    custom_terms.add_term(LISTA, "contrato indefinido")
    h_viejo = cp._term_hash("busco personal")
    custom_terms.remove_term(LISTA, "busco personal")

    update, context, q = _cbctx(MagicMock(wraps=tmp_db))
    q.data = f"cfg:ctdelok:{IDX}:{h_viejo}:{CID}"
    await cp.on_callback(update, context)

    assert custom_terms.list_terms(LISTA) == ["contrato indefinido"]
    q.answer.assert_awaited_with(cp.t("cfg.ct.gone"))


# --------------------- texto de humanos: HTML y 64 bytes ---------------------

_RAROS = [
    "<script>alert(1)</script>",
    "oferta & compañía",
    "trabajo desde casa ñáéíóú",
    "a" * custom_terms.MAX_TERM_LEN,
    "мошенничество онлайн",
    "trabajo 💰💰 fácil",
]


@pytest.mark.parametrize("termino", _RAROS)
def test_ningun_termino_se_pasa_de_los_64_bytes_de_callback(termino):
    """Telegram mide el callback_data en BYTES: un término largo o con acentos lo
    reventaría si viajara dentro. Por eso solo van índice y hash.

    Se prueban los CUATRO teclados de la función y con la lista de índice más alto,
    que es el peor caso posible."""
    peor = custom_terms.MANAGEABLE_LISTS[-1]
    teclados = [
        cp.build_term_lists_keyboard(CID),
        cp.build_terms_keyboard(CID, peor, [termino]),
        cp.build_term_confirm_keyboard(CID, peor, risky=True),
        cp.build_term_del_keyboard(CID, peor, termino),
    ]
    for kb in teclados:
        for dato in _datos(kb):
            assert len(dato.encode("utf-8")) <= 64, f"{dato!r} se pasa de 64 bytes"


@pytest.mark.parametrize("termino", _RAROS)
def test_el_callback_no_lleva_el_termino_dentro(termino):
    kb = cp.build_terms_keyboard(CID, LISTA, [termino])
    assert not any(termino[:10] in dato for dato in _datos(kb))


@pytest.mark.asyncio
async def test_un_termino_con_html_se_escapa_al_pintarlo(tmp_db):
    """Un `<` sin escapar rompe el envío ENTERO del mensaje (can't parse entities)."""
    assert custom_terms.add_term(LISTA, "gana <b>500</b> al mes").ok
    update, context, q = _cbctx(MagicMock(wraps=tmp_db))
    q.data = f"cfg:ctl:{IDX}:{CID}"
    await cp.on_callback(update, context)
    texto = q.edit_message_text.await_args.args[0]
    assert "&lt;b&gt;500&lt;/b&gt;" in texto
    assert "<b>500</b>" not in texto


@pytest.mark.asyncio
async def test_un_termino_escrito_a_mano_en_el_archivo_tampoco_rompe_el_html(tmp_db):
    """El archivo lo puede editar un humano con un editor, saltándose la validación:
    el panel tiene que aguantarlo igual (`custom_terms` lo dice explícitamente)."""
    ruta = custom_terms.custom_path(LISTA)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("<script>alert(1)</script>\n", encoding="utf-8")
    wordlists.clear_cache()

    update, context, q = _cbctx(MagicMock(wraps=tmp_db))
    q.data = f"cfg:ctl:{IDX}:{CID}"
    await cp.on_callback(update, context)

    texto = q.edit_message_text.await_args.args[0]
    assert "&lt;script&gt;" in texto
    assert "<script>" not in texto


@pytest.mark.asyncio
async def test_un_mensaje_de_ejemplo_con_html_se_escapa(tmp_db):
    """Los ejemplos son mensajes de gente: un `<` en uno tumbaría la vista previa."""
    _mensajes(tmp_db, ["busco personal <urgente> & barato"])
    user_data = {"cfg_await": {"field": "custom_term", "chat_id": CID},
                 "cfg_term": {"list": LISTA, "chat_id": CID}}
    update, context, reply = _capctx(tmp_db, user_data, "busco personal")

    await cp.handle_capture(update, context)

    texto = reply.await_args.args[0]
    assert "&lt;urgente&gt;" in texto
    assert "<urgente>" not in texto


@pytest.mark.asyncio
async def test_un_termino_con_acentos_se_guarda_y_se_quita_por_su_hash(tmp_db):
    termino = "trabajo desde casa ñáéíóú"
    user_data = {"cfg_term": {"list": LISTA, "term": termino, "chat_id": CID}}
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), user_data=user_data)
    q.data = f"cfg:ctok:{IDX}:{CID}"
    await cp.on_callback(update, context)
    assert custom_terms.list_terms(LISTA) == [termino]

    q.data = f"cfg:ctdelok:{IDX}:{cp._term_hash(termino)}:{CID}"
    await cp.on_callback(update, context)
    assert custom_terms.list_terms(LISTA) == []


# --------------------------- solo el admin del bot ---------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("data", [
    f"cfg:ct:{CID}",
    f"cfg:ctl:{IDX}:{CID}",
    f"cfg:ctadd:{IDX}:{CID}",
    f"cfg:ctok:{IDX}:{CID}",
])
async def test_un_no_admin_no_toca_nada(tmp_db, data):
    user_data = {"cfg_term": {"list": LISTA, "term": "busco personal", "chat_id": CID}}
    update, context, q = _cbctx(MagicMock(wraps=tmp_db), user_id=12345, user_data=user_data)
    q.data = data
    await cp.on_callback(update, context)
    assert custom_terms.list_terms(LISTA) == []
    q.edit_message_text.assert_not_awaited()


# ------------------------ índices de lista fuera de rango ------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("crudo", ["99", "-1", "abc", ""])
async def test_un_indice_de_lista_invalido_no_hace_nada(tmp_db, crudo):
    """El índice llega desde Telegram: fuera de la tupla cerrada no se resuelve nada."""
    update, context, q = _cbctx(MagicMock(wraps=tmp_db))
    q.data = f"cfg:ctl:{crudo}:{CID}"
    await cp.on_callback(update, context)
    q.edit_message_text.assert_not_awaited()
    assert cp._list_by_code(crudo) is None
