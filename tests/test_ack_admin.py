"""Un comando de moderación SIEMPRE tiene que contestar.

Caso real: `/ban` en respuesta a un mensaje. El ban se ejecutó y se federó bien,
pero el admin solo vio desaparecer su comando. El ack salía únicamente por el
notificador externo, que es OPCIONAL y no estaba configurado, así que `send_text`
devolvía False sin enviar nada. Con los quips desactivados por defecto tampoco
había rastro en el grupo.

Un moderador sin respuesta no sabe si el bot ha funcionado o está roto, y eso es
un fallo aunque la acción se haya ejecutado.
"""
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import admin
from src.db import DB


def _ctx(notifier_ok: bool | None):
    """notifier_ok: True = configurado y envía, False = no configurado, None = no hay."""
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    cfg = types.SimpleNamespace(admin_notify_chat_id=555, admin_user_id=1, shadow=False)
    notifier = None
    if notifier_ok is not None:
        notifier = MagicMock()
        notifier.send_text = AsyncMock(return_value=notifier_ok)
    ctx.bot_data = {"cfg": cfg, "notifier": notifier}
    return ctx, notifier


@pytest.mark.asyncio
async def test_sin_notificador_externo_contesta_el_propio_bot():
    """El fallo exacto que dejó al admin a ciegas."""
    ctx, _ = _ctx(notifier_ok=False)
    await admin._notify_admin_ack(ctx, "ban hecho")
    assert ctx.bot.send_message.await_count == 1, "el admin se quedó sin respuesta"
    assert ctx.bot.send_message.await_args.kwargs["chat_id"] == 555


@pytest.mark.asyncio
async def test_sin_notificador_configurado_ni_objeto_tambien_contesta():
    ctx, _ = _ctx(notifier_ok=None)
    await admin._notify_admin_ack(ctx, "ban hecho")
    assert ctx.bot.send_message.await_count == 1


@pytest.mark.asyncio
async def test_si_el_externo_funciona_no_se_duplica():
    """Quien lo tenga configurado no debe recibir el mismo aviso dos veces."""
    ctx, notifier = _ctx(notifier_ok=True)
    await admin._notify_admin_ack(ctx, "ban hecho")
    assert notifier.send_text.await_count == 1
    assert ctx.bot.send_message.await_count == 0, "aviso duplicado"


@pytest.mark.asyncio
async def test_si_el_externo_revienta_se_usa_el_respaldo():
    ctx, notifier = _ctx(notifier_ok=True)
    notifier.send_text = AsyncMock(side_effect=RuntimeError("red caída"))
    await admin._notify_admin_ack(ctx, "ban hecho")
    assert ctx.bot.send_message.await_count == 1, "una excepción dejó al admin sin respuesta"


@pytest.mark.asyncio
async def test_cae_al_user_id_si_no_hay_canal_de_avisos():
    ctx, _ = _ctx(notifier_ok=False)
    ctx.bot_data["cfg"] = types.SimpleNamespace(
        admin_notify_chat_id=None, admin_user_id=42, shadow=False)
    await admin._notify_admin_ack(ctx, "ban hecho")
    assert ctx.bot.send_message.await_args.kwargs["chat_id"] == 42


@pytest.mark.asyncio
async def test_un_fallo_de_telegram_no_tumba_el_comando():
    from telegram.error import TelegramError
    ctx, _ = _ctx(notifier_ok=False)
    ctx.bot.send_message = AsyncMock(side_effect=TelegramError("bloqueado"))
    await admin._notify_admin_ack(ctx, "ban hecho")   # no debe propagar


def test_el_ban_manual_queda_en_la_auditoria(tmp_path):
    """Estaba en `banned_users` pero NO en `moderation_log`: no salía en /recent
    ni contaba en /stats, así que no había forma de revisarlo después."""
    import ast
    import pathlib
    # `inspect.getsource` devolvería el wrapper del decorador @_only_admin, no el
    # comando: hay que leer el árbol del fichero.
    arbol = ast.parse(pathlib.Path("src/admin.py").read_text())
    cuerpos = {n.name: ast.dump(n) for n in ast.walk(arbol)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for cmd in ("cmd_ban", "cmd_unban"):
        assert "log_action" in cuerpos[cmd], f"/{cmd[4:]} no registra la acción"


def test_las_reglas_manuales_tienen_explicacion():
    from src.rule_explain import KNOWN_RULES, explain
    for regla in ("manual_admin_ban", "manual_admin_unban"):
        assert regla in KNOWN_RULES
        assert explain(regla) != regla, f"{regla} saldría como id técnico"
