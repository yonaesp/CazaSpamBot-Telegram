"""Una historia (story) reenviada: el bot no puede leerla, y tiene que decirlo.

Telegram entrega a los bots un objeto `Story` con SOLO `chat` e `id`: ni texto, ni
imagen, ni entidades. El admin, en cambio, ve en su pantalla un mensaje lleno de
texto. Si el scan contesta «no dispararía ninguna regla», el admin entiende
«esto es limpio», cuando lo cierto es «no he podido leerlo».

Caso real: un spammer reenvió una historia con publicidad de cripto y el scan la
dio por inocua.
"""
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
    )
    ctx = MagicMock()
    ctx.bot_data = {"cfg": cfg, "db": DB(str(tmp_path / "t.db"))}
    ctx.user_data = {}
    return ctx


def _mensaje(story=False, texto=None):
    """Una historia reenviada llega así: sin texto, sin media, sin marca de reenvío."""
    msg = MagicMock()
    msg.text = texto
    msg.caption = None
    msg.reply_to_message = None
    msg.chat_id = 99
    msg.chat = types.SimpleNamespace(type="private", id=99)
    msg.reply_text = AsyncMock()
    for attr in ("contact", "reply_markup", "external_reply", "quote", "forward_origin",
                 "forward_from_chat", "forward_from", "forward_sender_name", "via_bot", "photo", "video", "document",
                 "animation", "sticker", "voice", "video_note", "audio",
                 "entities", "caption_entities"):
        setattr(msg, attr, None)
    msg.story = types.SimpleNamespace(id=7, chat=types.SimpleNamespace(id=-100123)) if story else None
    return msg


@pytest.mark.asyncio
async def test_la_historia_se_identifica_como_tal(tmp_path):
    ctx = _ctx(tmp_path)
    msg = _mensaje(story=True)
    await scan_cmd._responder_scan(msg, msg, ctx.bot_data["cfg"], ctx.bot_data["db"])
    salida = msg.reply_text.await_args.args[0]
    assert "istoria" in salida or "tory" in salida, (
        f"no dice que sea una historia: {salida!r}"
    )


@pytest.mark.asyncio
async def test_no_dice_que_estaria_limpio(tmp_path):
    """Lo importante: no puede afirmar que no dispararía ninguna regla."""
    ctx = _ctx(tmp_path)
    msg = _mensaje(story=True)
    await scan_cmd._responder_scan(msg, msg, ctx.bot_data["cfg"], ctx.bot_data["db"])
    salida = msg.reply_text.await_args.args[0]
    assert "NO dispararía" not in salida, (
        "sigue dando por inocua una historia que no ha podido leer"
    )
    assert "no lo he leído" in salida or "not read it" in salida, (
        f"no avisa de que no ha leído el contenido: {salida!r}"
    )


@pytest.mark.asyncio
async def test_un_mensaje_normal_sin_hits_sigue_diciendo_que_no_dispara(tmp_path):
    """Contrapeso: el aviso de la historia no puede comerse el veredicto normal."""
    ctx = _ctx(tmp_path)
    msg = _mensaje(story=False, texto="buenas, alguien sabe como configurar el router?")
    await scan_cmd._responder_scan(msg, msg, ctx.bot_data["cfg"], ctx.bot_data["db"])
    salida = msg.reply_text.await_args.args[0]
    assert "NO dispararía" in salida, f"perdió el veredicto normal: {salida!r}"
    assert "no lo he leído" not in salida
