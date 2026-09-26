"""Tras un ban se retiran los mensajes del baneado Y los avisos que el bot dejó.

Caso real (26-sep-2026, Windows 11): una cuenta mandó cuatro reenvíos de
publicidad porno (60898, 60900, 60902, 60904). Se abrieron tres revisiones, el
admin pulsó «Spam» en la primera a las 08:57 y a las 11:00 seguían en el grupo
tres de los cuatro mensajes y dos avisos de «un administrador lo revisará»
respondiendo a un «mensaje eliminado». Banear en un supergrupo NO borra los
mensajes, y la función que debía hacerlo no la llamaba nadie.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from telegram.error import TelegramError

from src import federation
from src.db import DB

CHAT, OTRO, UID = -1001190184646, -1001008178265, 8488005572


@pytest.fixture
def db(tmp_path):
    d = DB(str(tmp_path / "t.db"))
    for mid in (60898, 60900, 60902, 60904):          # los cuatro, sin texto
        d.guardar_mensaje_reciente(CHAT, UID, mid, "")
    d.guardar_mensaje_reciente(OTRO, UID, 500, "hola")
    d.guardar_mensaje_reciente(CHAT, 999, 61000, "de otra persona")
    for mid, aviso in ((60898, 60899), (60900, 60901), (60902, 60903)):
        d.add_gentle_warning(CHAT, mid, aviso, UID)
    return d


class _Bot:
    """Imita a Telegram: `delete_messages` borra lo que le piden y nada más."""
    def __init__(self, falla_en=()):
        self.borrados: dict[int, set[int]] = {}
        self.falla_en = set(falla_en)

    async def delete_messages(self, chat_id, message_ids):
        if chat_id in self.falla_en:
            raise TelegramError("Message can't be deleted")
        assert len(message_ids) <= 100, "deleteMessages admite 100 por llamada"
        self.borrados.setdefault(chat_id, set()).update(message_ids)
        return True


def test_el_caso_real_se_lleva_los_cuatro_mensajes_y_los_avisos(db):
    bot = _Bot()
    asyncio.run(federation._retirar_mensajes(bot, db, UID, [CHAT]))
    assert {60898, 60900, 60902, 60904} <= bot.borrados[CHAT]
    assert {60899, 60901, 60903} <= bot.borrados[CHAT]


def test_no_toca_mensajes_de_otra_persona(db):
    bot = _Bot()
    asyncio.run(federation._retirar_mensajes(bot, db, UID, [CHAT, OTRO]))
    assert 61000 not in bot.borrados[CHAT]
    assert bot.borrados[OTRO] == {500}


def test_solo_en_los_chats_donde_se_aplico_el_ban(db):
    bot = _Bot()
    asyncio.run(federation._retirar_mensajes(bot, db, UID, [CHAT]))
    assert OTRO not in bot.borrados


def test_un_fallo_de_telegram_no_tumba_nada(db):
    """La limpieza va DESPUÉS del ban: si falla, el ban ya está hecho y sigue."""
    asyncio.run(federation._retirar_mensajes(_Bot(falla_en={CHAT}), db, UID, [CHAT]))


def test_los_mensajes_que_nadie_juzgo_tambien_salen(db):
    """El cuarto mensaje no estaba en `moderation_log`: la función vieja no lo veía."""
    ids = db.mensajes_para_limpiar(UID, time.time() - 3600)[CHAT]
    assert 60904 in ids


def test_los_avisos_se_sacan_una_sola_vez(db):
    assert sorted(db.pop_avisos_de_usuario(CHAT, UID)) == [60899, 60901, 60903]
    assert db.pop_avisos_de_usuario(CHAT, UID) == []


def test_federate_ban_limpia_despues_de_banear():
    """El orden importa: primero el ban, luego la limpieza. Al revés, un spammer
    rápido podría volver a escribir entre medias."""
    import inspect
    fuente = inspect.getsource(federation.federate_ban)
    assert fuente.index("_ban_one(cid)") < fuente.index("await _retirar_mensajes(")
