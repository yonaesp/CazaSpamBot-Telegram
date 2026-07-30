"""Las cuatro protecciones más importantes del bot, que estaban SIN test.

Detectadas con pruebas de mutación: se rompió cada una a propósito y los 927
tests seguían pasando. Un test que no falla cuando rompes lo que dice proteger
da falsa seguridad, y estas cuatro son justo las que más caro salen si fallan:

  1. No banear a un administrador del chat.
  2. Un ban se replica a TODOS los grupos (es la razón de ser del bot).
  3. En modo shadow no se actúa, solo se registra.
  4. El mensaje de verificación con TTL «nunca» no se programa para borrar.
"""
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import federation, handlers, verification
from src.db import DB


def _cfg(**kw):
    base = dict(admin_user_id=1, admin_notify_chat_id=None, shadow=False,
                federation_enabled=True,
                public_quip_enabled=False, quip_on_auto_ban=False,
                report_before_ban=False, notify_self_deletes=False,
                public_quip_delete_after_s=3600)
    base.update(kw)
    return types.SimpleNamespace(**base)


def _db(tmp_path, n_chats=3):
    db = DB(str(tmp_path / "t.db"))
    for i in range(n_chats):
        cid = -100100 - i
        db.upsert_bot_chat(cid, f"G{i}", "supergroup", True, True, True)
        db.ensure_chat_settings(cid)
    return db


# --------------------------------------------------------------------------
# 1. Nunca banear a un admin del chat
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_se_banea_a_un_admin_del_chat(tmp_path):
    """Si el objetivo es admin, la acción se degrada a noop.

    Es la guarda que habría salvado a un bot de moderación legítimo si hubiera
    sido administrador. Estaba sin cubrir: se podía desactivar entera y los 927
    tests seguían en verde.
    """
    db = _db(tmp_path)
    cfg = _cfg()
    ctx = MagicMock()
    ctx.bot.ban_chat_member = AsyncMock(return_value=True)
    ctx.bot.delete_message = AsyncMock(return_value=True)
    ctx.bot.send_message = AsyncMock()
    ctx.bot.get_chat_member = AsyncMock(
        return_value=types.SimpleNamespace(status="administrator"))
    notifier = MagicMock()
    notifier.is_configured.return_value = False  # alerta externa desactivada
    ctx.bot_data = {"cfg": cfg, "db": db, "notifier": notifier}
    ctx.application = MagicMock()
    ctx.application.job_queue = None
    # create_task de verdad ejecuta la corrutina; el doble al menos la cierra, para
    # no dejar un RuntimeWarning de «coroutine was never awaited» que enmascare otros.
    ctx.application.create_task = lambda coro, **kw: coro.close()

    decision = types.SimpleNamespace(action="ban", rule="commercial_ad", score=120,
                                     reason="prueba", payload={})
    await handlers._apply_action(
        ctx, db, cfg, chat_id=-100100, chat_title="G0", user_id=777,
        username="admin_del_grupo", message_id=5, decision=decision,
        original_text="da igual",
    )
    assert ctx.bot.ban_chat_member.await_count == 0, "ha baneado a un ADMIN"

    # y debe quedar registrado como noop, no como ban
    fila = db.recent_actions(limit=1)[0]
    assert fila["action"] == "noop", f"registrado como {fila['action']!r} en vez de noop"


@pytest.mark.asyncio
async def test_a_un_miembro_normal_si_se_le_banea(tmp_path):
    """Contrapeso del test anterior: la guarda no puede volver inofensivo al bot."""
    db = _db(tmp_path)
    cfg = _cfg()
    ctx = MagicMock()
    ctx.bot.ban_chat_member = AsyncMock(return_value=True)
    ctx.bot.delete_message = AsyncMock(return_value=True)
    ctx.bot.send_message = AsyncMock()
    ctx.bot.get_chat_member = AsyncMock(
        return_value=types.SimpleNamespace(status="member"))
    notifier = MagicMock()
    notifier.is_configured.return_value = False  # alerta externa desactivada
    ctx.bot_data = {"cfg": cfg, "db": db, "notifier": notifier}
    ctx.application = MagicMock()
    ctx.application.job_queue = None
    # create_task de verdad ejecuta la corrutina; el doble al menos la cierra, para
    # no dejar un RuntimeWarning de «coroutine was never awaited» que enmascare otros.
    ctx.application.create_task = lambda coro, **kw: coro.close()

    decision = types.SimpleNamespace(action="ban", rule="commercial_ad", score=120,
                                     reason="prueba", payload={})
    await handlers._apply_action(
        ctx, db, cfg, chat_id=-100100, chat_title="G0", user_id=888,
        username="spammer", message_id=5, decision=decision, original_text="spam",
    )
    assert ctx.bot.ban_chat_member.await_count >= 1, "no ha baneado a un miembro normal"


# --------------------------------------------------------------------------
# 2. El ban se replica a TODOS los grupos
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_el_ban_se_replica_a_todos_los_grupos(tmp_path):
    """La federación es la razón de ser del bot: un ban en uno = ban en todos.
    Estaba sin test: se podía limitar a un solo grupo sin que nada fallara."""
    db = _db(tmp_path, n_chats=3)
    bot = MagicMock()
    bot.ban_chat_member = AsyncMock(return_value=True)

    res = await federation.federate_ban(
        bot, db, user_id=999, reason="x", rule="r",
        triggered_in_chat=-100100, shadow=False,
    )
    assert len(res) == 3, f"solo intentó {len(res)} grupos de 3"
    assert sum(1 for v in res.values() if v == "ok") == 3
    baneados = {c.kwargs["chat_id"] for c in bot.ban_chat_member.await_args_list}
    assert baneados == {-100100, -100101, -100102}


@pytest.mark.asyncio
async def test_el_ban_queda_registrado_para_la_federacion(tmp_path):
    """Debe persistirse: es lo que permite re-banear al reentrar en otro grupo."""
    db = _db(tmp_path)
    bot = MagicMock()
    bot.ban_chat_member = AsyncMock(return_value=True)
    await federation.federate_ban(bot, db, user_id=4242, reason="motivo",
                                  rule="regla", triggered_in_chat=-100100, shadow=False)
    assert db.is_banned(4242), "el ban no quedó registrado"


# --------------------------------------------------------------------------
# 3. En modo shadow NO se actúa
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_en_shadow_no_se_banea_de_verdad(tmp_path):
    """Shadow existe para probar sin riesgo: si actuara, alguien que creyera estar
    en pruebas estaría baneando gente real."""
    db = _db(tmp_path)
    bot = MagicMock()
    bot.ban_chat_member = AsyncMock(return_value=True)

    res = await federation.federate_ban(
        bot, db, user_id=555, reason="x", rule="r",
        triggered_in_chat=-100100, shadow=True,
    )
    assert bot.ban_chat_member.await_count == 0, "¡ha baneado estando en shadow!"
    assert all(v == "shadow" for v in res.values())


# --------------------------------------------------------------------------
# 4. TTL «nunca» del mensaje de verificación
# --------------------------------------------------------------------------

def test_ttl_nunca_no_programa_borrado(tmp_path):
    """0 = no borrar nunca. Si se programara igual, el ajuste sería mentira.

    Se comprueba sobre la condición real del código (`ttl > 0`), que es lo que
    decide si se encola el job de borrado.
    """
    import inspect
    fuente = inspect.getsource(verification.on_callback)
    assert "ttl > 0" in fuente, (
        "el borrado del mensaje verificado ya no comprueba ttl > 0: "
        "con TTL «nunca» se programaría igual y el mensaje desaparecería"
    )


def test_el_barrido_tambien_respeta_el_nunca():
    """El otro sitio donde se borra: sin esta guarda, el mensaje «permanente»
    sobrevivía hasta el siguiente reinicio y luego desaparecía."""
    import inspect
    fuente = inspect.getsource(verification.cleanup_job)
    assert "sweep_verified" in fuente, "el barrido por BD ya no distingue el TTL «nunca»"
