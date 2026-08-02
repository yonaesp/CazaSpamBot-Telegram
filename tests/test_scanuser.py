"""/scanuser: radiografía de UNA persona. Solo informa, nunca actúa.

Hermano de /scan: aquel mira un mensaje, este mira a quien lo manda. Cubre el caso
que no cubría nada: «este me da mala espina, ¿qué sabes de él?», sin tener que
banear para averiguarlo.
"""
import re
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import scanuser_cmd
from src.db import DB


def _montar(tmp_path, con_telethon=False, baneado=False, whitelist=False):
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(-100100, "G", "supergroup", True, True, True)
    db.record_message(-100100, 777, "pepe")
    if baneado:
        db.add_ban(user_id=777, reason="x", rule="r", banned_in_chat=-100100, federated=True)
    if whitelist:
        db.set_whitelist(-100100, 777, True) if hasattr(db, "set_whitelist") else None

    objetivo = types.SimpleNamespace(id=777, username=None, first_name="Williams",
                                     last_name=None)
    msg = MagicMock()
    msg.chat_id = -100100
    msg.entities = None
    msg.reply_to_message = MagicMock()
    msg.reply_to_message.from_user = objetivo
    msg.reply_text = AsyncMock()
    upd = MagicMock()
    upd.effective_message = msg

    ctx = MagicMock()
    ctx.args = []
    ctx.bot.get_chat_member = AsyncMock(return_value=types.SimpleNamespace(user=objetivo))
    ctx.bot.ban_chat_member = AsyncMock()
    ctx.bot.delete_message = AsyncMock()
    ctx.bot.send_message = AsyncMock()
    reporter = None
    if con_telethon:
        reporter = MagicMock()
        reporter.get_client.return_value = MagicMock()
    ctx.user_data = {}          # dict de verdad: un MagicMock rompe el `get`
    ctx.bot_data = {
        "cfg": types.SimpleNamespace(cas_enabled=False, lols_enabled=False,
                                     cas_cache_ttl_seconds=3600,
                                     admin_notify_chat_id=555, admin_user_id=1),
        "db": db, "reporter": reporter, "http": None,
    }
    return upd, ctx, db, msg


def _texto(msg):
    return re.sub(r"<[^>]+>", "", msg.reply_text.await_args.args[0])


@pytest.mark.asyncio
async def test_informa_de_lo_que_el_bot_sabe(tmp_path):
    upd, ctx, _db, msg = _montar(tmp_path)
    await scanuser_cmd.cmd_scanuser(upd, ctx)
    salida = _texto(msg)
    assert "Williams" in salida and "777" in salida
    assert "Cuánto me fío" in salida, "no muestra el trust"
    assert "sobre 100" in salida, "no muestra la cifra de confianza"
    assert "mensajes en total" in salida, "no dice cuánto ha escrito"
    assert "últimos 30 días" in salida, "no dice la actividad reciente"
    assert "La cuenta" in salida, "no dice cuándo se creó la cuenta"


@pytest.mark.asyncio
async def test_no_actua_nunca(tmp_path):
    """Consultar a alguien no es moderarlo: si tuviera efectos, nadie lo usaría."""
    upd, ctx, db, _msg = _montar(tmp_path)
    await scanuser_cmd.cmd_scanuser(upd, ctx)
    assert ctx.bot.ban_chat_member.await_count == 0
    assert ctx.bot.delete_message.await_count == 0
    assert not db.recent_actions(limit=5), "escribió en el registro de moderación"
    assert not db.is_banned(777)


@pytest.mark.asyncio
async def test_sin_telethon_lo_dice_en_vez_de_fingir(tmp_path):
    """El mismo error que cometía /scan con las historias: dar por limpio lo que
    no se ha mirado es peor que no mirarlo."""
    upd, ctx, _db, msg = _montar(tmp_path, con_telethon=False)
    await scanuser_cmd.cmd_scanuser(upd, ctx)
    salida = _texto(msg)
    assert "no lo he visto" in salida, "finge que el perfil está limpio"
    assert "no puedo decirlo" in salida, "emite veredicto sin haber visto el perfil"


@pytest.mark.asyncio
async def test_avisa_si_ya_esta_baneado(tmp_path):
    upd, ctx, _db, msg = _montar(tmp_path, baneado=True)
    await scanuser_cmd.cmd_scanuser(upd, ctx)
    assert "baneado" in _texto(msg).lower()


@pytest.mark.asyncio
async def test_sin_objetivo_se_queda_esperando(tmp_path):
    """El orden natural: escribes el comando y DESPUÉS le dices de quién hablas."""
    upd, ctx, _db, _msg = _montar(tmp_path)
    upd.effective_message.reply_to_message = None
    upd.effective_message.entities = None
    ctx.args = []
    await scanuser_cmd.cmd_scanuser(upd, ctx)
    assert "scanuser_await" in ctx.user_data, "no se quedó esperando"
    enviado = ctx.bot.send_message.await_args.kwargs["text"]
    assert "@usuario" in enviado or "@username" in enviado


@pytest.mark.asyncio
async def test_captura_por_reenvio(tmp_path):
    """Le reenvías un mensaje suyo y saca el informe de su autor."""
    upd, ctx, _db, msg = _montar(tmp_path)
    ctx.user_data["scanuser_await"] = {"t": __import__("time").time(), "chat": -100100}
    msg.forward_origin = types.SimpleNamespace(
        sender_user=types.SimpleNamespace(id=777, username=None, first_name="W"))
    msg.forward_from = None
    consumido = await scanuser_cmd.handle_capture(upd, ctx)
    assert consumido is True
    assert "777" in _texto(msg)


@pytest.mark.asyncio
async def test_captura_por_username(tmp_path):
    upd, ctx, db, msg = _montar(tmp_path)
    db.remember_username("pepe", 777)
    ctx.user_data["scanuser_await"] = {"t": __import__("time").time(), "chat": -100100}
    msg.forward_origin = None
    msg.forward_from = None
    msg.text = "@pepe"
    assert await scanuser_cmd.handle_capture(upd, ctx) is True
    assert "777" in _texto(msg)


@pytest.mark.asyncio
async def test_la_espera_caduca(tmp_path):
    upd, ctx, _db, msg = _montar(tmp_path)
    ctx.user_data["scanuser_await"] = {
        "t": __import__("time").time() - scanuser_cmd.ESPERA_TTL_S - 1, "chat": -100100}
    msg.forward_origin = None
    msg.forward_from = None
    msg.text = "hola"
    assert await scanuser_cmd.handle_capture(upd, ctx) is False


@pytest.mark.asyncio
async def test_en_grupo_borra_el_comando_y_responde_por_privado(tmp_path):
    """Un informe con el nombre de alguien a quien se mira con lupa no pinta nada
    en el grupo, y así el admin no tiene que borrarlo a mano después."""
    upd, ctx, _db, msg = _montar(tmp_path)
    msg.chat = types.SimpleNamespace(id=-100100, type="supergroup", title="G")
    msg.delete = AsyncMock()
    ctx.bot_data["cfg"] = types.SimpleNamespace(
        cas_enabled=False, lols_enabled=False, cas_cache_ttl_seconds=3600,
        admin_notify_chat_id=555, admin_user_id=1)
    await scanuser_cmd.cmd_scanuser(upd, ctx)
    assert msg.delete.await_count == 1, "no borró el comando del grupo"
    destinos = [c.kwargs.get("chat_id") for c in ctx.bot.send_message.await_args_list]
    assert 555 in destinos, f"no respondió por privado: {destinos}"
    assert -100100 not in destinos, "publicó el informe en el grupo"


@pytest.mark.asyncio
async def test_no_pone_enlaces_al_perfil_del_spammer(tmp_path):
    """Regla 6: nombre + id, nunca un enlace que le dé visibilidad."""
    upd, ctx, _db, msg = _montar(tmp_path)
    await scanuser_cmd.cmd_scanuser(upd, ctx)
    crudo = msg.reply_text.await_args.args[0]
    assert "tg://user" not in crudo and "t.me/" not in crudo


def test_el_comando_esta_registrado():
    from pathlib import Path
    main = Path("src/main.py").read_text()
    assert 'CommandHandler("scanuser"' in main, "el comando no está registrado"
    assert 'CommandHandler("analizarusuario"' in main, "falta el alias en español"
