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
    ctx.bot_data = {
        "cfg": types.SimpleNamespace(cas_enabled=False, lols_enabled=False,
                                     cas_cache_ttl_seconds=3600),
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
    assert "Confianza" in salida, "no muestra el trust"
    assert "mensajes" in salida, "no dice cuánto ha escrito"


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
async def test_sin_objetivo_explica_como_usarlo(tmp_path):
    upd, ctx, _db, msg = _montar(tmp_path)
    upd.effective_message.reply_to_message = None
    upd.effective_message.entities = None
    ctx.args = []
    await scanuser_cmd.cmd_scanuser(upd, ctx)
    assert "/scanuser" in _texto(msg)


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
