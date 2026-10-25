"""Qué avisos por privado suenan y cuáles llegan en silencio (`notify_prefs.sin_sonido`).

Petición del admin (25-oct-2026): que suene lo que tiene riesgo y llegue callado lo
leve, configurable. Hasta entonces sonaba casi todo. Por defecto suena solo lo
IMPORTANTE: lo que necesita que decidas o deja un grupo con menos protección.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import admin, handlers, notify_prefs

# Lo único que suena con el modo por defecto. Si cambias esta lista, que sea
# a propósito: es la diferencia entre un aviso que se atiende y uno que se ignora.
IMPORTANTES = {
    ("admin_report.py", "handle_admin_mention"),     # un miembro pide ayuda con @admin
    ("antiraid.py", "avisar"),                       # avalancha de entradas
    ("handlers.py", "_avisar_si_le_recortan"),       # me quitan permisos
    ("handlers.py", "on_my_chat_member"),            # me echan de un grupo
    ("handlers.py", "_check_admin_ban_abuse"),       # un admin banea en masa
    ("handlers.py", "_send_review_request"),         # ¿es spam? (yo no he actuado)
    ("handlers.py", "_avisar_readmision"),           # readmiten a un baneado
    ("main.py", "_on_error"),                        # error interno
    ("verification.py", "avisar_han_mudo"),          # alguien espera mudo tu decisión
}
# Lo que contesta a una orden tuya: lo estás esperando, no es un aviso.
RESPUESTAS = {"_notify_admin_ack", "_entregar", "cmd_scanuser"}
DESTINOS_ADMIN = {"admin_dm", "cfg.admin_notify_chat_id", "destino", "admin_id"}


def _envios_al_admin():
    for f in sorted(Path("src").rglob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("send_message", "copy_message", "send_photo",
                                               "send_document", "forward_message")):
                    kw = {k.arg: k.value for k in node.keywords if k.arg}
                    if "chat_id" in kw and ast.unparse(kw["chat_id"]) in DESTINOS_ADMIN:
                        yield f.name, fn.name, node.lineno, kw.get("disable_notification")


def test_cada_aviso_al_admin_decide_si_suena():
    """Un envío nuevo al privado sin decidir su sonido sonaría siempre."""
    sin = [(f, fn, ln) for f, fn, ln, dn in _envios_al_admin()
           if dn is None and fn not in RESPUESTAS]
    assert not sin, f"avisos al admin sin disable_notification: {sin}"


def test_suena_solo_lo_importante():
    importantes, informativos = set(), set()
    for f, fn, _, dn in _envios_al_admin():
        if dn is None or not isinstance(dn, ast.Call):
            continue
        imp = next(k.value for k in dn.keywords if k.arg == "importante")
        if isinstance(imp, ast.Constant):
            (importantes if imp.value else informativos).add((f, fn))
    assert importantes == IMPORTANTES
    # Lo que el bot ya resolvió, entre lo callado
    assert ("handlers.py", "_apply_action") in informativos
    assert ("handlers.py", "_avisar_imagen_dudosa") in informativos


@pytest.mark.parametrize("modo,importante,callado", [
    ("importante", True, False), ("importante", False, True),
    ("todo", True, False), ("todo", False, False),
    ("nada", True, True), ("nada", False, True),
])
def test_modos(tmp_db, modo, importante, callado):
    tmp_db.set_text_pref(notify_prefs.SONIDO_PREF, modo)
    assert notify_prefs.sin_sonido(tmp_db, importante) is callado


def test_por_defecto_y_ante_basura(tmp_db):
    assert notify_prefs.modo_sonido(tmp_db) == "importante"
    tmp_db.set_text_pref(notify_prefs.SONIDO_PREF, "xyz")
    assert notify_prefs.modo_sonido(tmp_db) == "importante"
    # Sin base que leer (algún aviso se manda sin ella): el defecto, sin reventar
    assert notify_prefs.sin_sonido(None, True) is False
    assert notify_prefs.sin_sonido(object(), False) is True


@pytest.mark.parametrize("accion,avala,callado", [
    ("gentle_warn", True, True),     # el caso @Moliko: leve
    ("ban", True, False),            # un veterano habría caído: ¿cuenta robada?
    ("kick", True, False),
    ("ban", False, True),            # perdón por falta de evidencia: leve
])
@pytest.mark.asyncio
async def test_aviso_de_confianza(monkeypatch, tmp_db, accion, avala, callado):
    monkeypatch.setattr(handlers.notify_prefs, "effective", lambda *a, **k: True)
    bot = NS(send_message=AsyncMock(return_value=NS(message_id=1)))
    ctx = NS(bot=bot, bot_data={}, application=NS(job_queue=None))
    msg = NS(text="x", caption=None, chat_id=-100, message_id=1, chat=NS(id=-100, title="W11"))
    await handlers._send_trust_notice(
        ctx, tmp_db, NS(admin_notify_chat_id=7, mode="active"), msg,
        NS(id=1, first_name="a", username=None), ["r"], "x", accion, 90, avala_historial=avala)
    assert bot.send_message.await_args.kwargs["disable_notification"] is callado


@pytest.mark.asyncio
async def test_alertas_cambia_el_modo_en_ciclo(tmp_db):
    q = MagicMock()
    q.data = "npref:son:"
    q.from_user.id = 5
    q.answer = AsyncMock()
    q.edit_message_reply_markup = AsyncMock()
    ctx = NS(bot_data={"db": tmp_db, "cfg": NS(admin_user_id=5)})
    vistos = []
    for _ in range(3):
        await admin.on_notifpref_callback(NS(callback_query=q), ctx)
        vistos.append(notify_prefs.modo_sonido(tmp_db))
    assert vistos == ["todo", "nada", "importante"]
    teclado = q.edit_message_reply_markup.await_args.kwargs["reply_markup"]
    assert teclado.inline_keyboard[0][0].callback_data == "npref:son:"
