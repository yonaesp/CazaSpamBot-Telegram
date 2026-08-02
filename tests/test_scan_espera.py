"""/scan sin responder a nada: el bot se queda esperando el mensaje.

Antes solo funcionaba en un orden: primero reenviar, luego responder con /scan.
Al revés (escribir /scan y reenviar después) el reenvío caía en el handler
genérico del DM y el admin recibía el saludo de «solo respondo a comandos»,
como si el comando no hubiera existido.
"""
import time
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import scan_cmd
from src.db import DB


def _ctx(tmp_path):
    cfg = types.SimpleNamespace(
        admin_user_id=1, allowed_scripts=["latin"], non_latin_ratio_threshold=0.5,
        url_blocklist=[], detect_external_mentions=False,
        detect_external_tg_links=False, is_moderated=lambda _cid: False,
        ban_score=100, kick_score=70, mute_score=40,
    )
    ctx = MagicMock()
    ctx.bot_data = {"cfg": cfg, "db": DB(str(tmp_path / "t.db"))}
    ctx.user_data = {}
    return ctx


def _update(texto=None, chat_type="private", reply=None, user_id=1):
    msg = MagicMock()
    msg.text = texto
    msg.caption = None
    msg.reply_to_message = reply
    msg.chat_id = 99
    msg.message_id = 500
    msg.chat = types.SimpleNamespace(type=chat_type, id=99)
    msg.reply_text = AsyncMock()
    # atributos que miran los detectores de estructura
    for attr in ("contact", "reply_markup", "external_reply", "quote", "forward_origin",
                 "photo", "video", "document", "animation", "sticker", "voice",
                 "video_note", "audio", "entities", "caption_entities", "story"):
        setattr(msg, attr, None)
    upd = MagicMock()
    upd.effective_message = msg
    upd.effective_user = types.SimpleNamespace(id=user_id)
    upd.effective_chat = types.SimpleNamespace(type=chat_type, id=99)
    return upd, msg


@pytest.mark.asyncio
async def test_scan_a_secas_en_dm_deja_al_bot_esperando(tmp_path):
    ctx = _ctx(tmp_path)
    upd, msg = _update(texto="/scan")
    await scan_cmd.cmd_scan(upd, ctx)
    assert "scan_await" in ctx.user_data, "el bot no se quedó esperando el mensaje"
    assert msg.reply_text.await_count == 1


@pytest.mark.asyncio
async def test_el_mensaje_reenviado_despues_si_se_escanea(tmp_path):
    """El caso que fallaba: /scan primero, reenvío después."""
    ctx = _ctx(tmp_path)
    upd, _ = _update(texto="/scan")
    await scan_cmd.cmd_scan(upd, ctx)

    upd2, msg2 = _update(texto="Free signals, click to subscribe https://t.me/+abc")
    consumido = await scan_cmd.handle_capture(upd2, ctx)

    assert consumido is True, "el reenvío no se consumió: caería en el saludo genérico"
    salida = msg2.reply_text.await_args.args[0]
    assert "scan" in salida.lower(), "no contestó con el informe del scan"
    assert "scan_await" not in ctx.user_data, "la espera debe ser de un solo uso"


@pytest.mark.asyncio
async def test_sin_scan_previo_no_captura_nada(tmp_path):
    """Un mensaje suelto en el DM no debe acabar escaneado."""
    ctx = _ctx(tmp_path)
    upd, _ = _update(texto="hola")
    assert await scan_cmd.handle_capture(upd, ctx) is False


@pytest.mark.asyncio
async def test_la_espera_caduca(tmp_path):
    """Si el admin se olvidó, media hora después quiere la ayuda normal,
    no que su mensaje se convierta en un scan por sorpresa."""
    ctx = _ctx(tmp_path)
    ctx.user_data["scan_await"] = time.time() - scan_cmd._ESPERA_TTL_S - 1
    upd, msg = _update(texto="cualquier cosa")
    assert await scan_cmd.handle_capture(upd, ctx) is False
    assert msg.reply_text.await_count == 0
    assert "scan_await" not in ctx.user_data, "la espera caducada debe limpiarse"


@pytest.mark.asyncio
async def test_en_grupo_no_se_queda_esperando(tmp_path):
    """En grupo capturar el siguiente mensaje sería impredecible para el resto."""
    ctx = _ctx(tmp_path)
    upd, msg = _update(texto="/scan", chat_type="supergroup")
    await scan_cmd.cmd_scan(upd, ctx)
    assert "scan_await" not in ctx.user_data, "no debe esperar en un grupo"
    assert msg.reply_text.await_count == 1  # la ayuda de siempre


@pytest.mark.asyncio
async def test_el_handler_del_dm_enruta_la_espera(tmp_path):
    """El cableado, que es lo que faltaba: sin esto `handle_capture` existe pero
    nadie lo llama, y el reenvío sigue recibiendo el saludo genérico."""
    from src import admin
    ctx = _ctx(tmp_path)
    ctx.user_data["scan_await"] = time.time()
    upd, msg = _update(texto="Free signals https://t.me/+abc")
    await admin.on_private_message(upd, ctx)
    salida = msg.reply_text.await_args.args[0]
    assert "Resultado" in salida or "Result" in salida, (
        f"el DM contestó el saludo genérico en vez del scan: {salida[:80]!r}"
    )


@pytest.mark.asyncio
async def test_sin_espera_el_dm_contesta_lo_de_siempre(tmp_path):
    """Contrapeso: la captura no puede tragarse el saludo normal."""
    from src import admin
    ctx = _ctx(tmp_path)
    upd, msg = _update(texto="hola")
    await admin.on_private_message(upd, ctx)
    salida = msg.reply_text.await_args.args[0]
    assert "Resultado" not in salida, "escaneó un mensaje que nadie pidió escanear"


@pytest.mark.asyncio
async def test_responder_con_scan_sigue_funcionando(tmp_path):
    """La forma que ya funcionaba no puede romperse."""
    ctx = _ctx(tmp_path)
    _, objetivo = _update(texto="gana 500 USD por dia, escribime @quien")
    upd, msg = _update(texto="/scan", reply=objetivo)
    await scan_cmd.cmd_scan(upd, ctx)
    assert msg.reply_text.await_count == 1
    assert "scan_await" not in ctx.user_data, "con reply no hay nada que esperar"
