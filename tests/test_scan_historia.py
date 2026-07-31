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
        ban_score=100, kick_score=70, mute_score=40,
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
    await scan_cmd._responder_scan(ctx, msg, msg, ctx.bot_data["cfg"], ctx.bot_data["db"])
    salida = msg.reply_text.await_args.args[0]
    assert "istoria" in salida or "tory" in salida, (
        f"no dice que sea una historia: {salida!r}"
    )


@pytest.mark.asyncio
async def test_no_dice_que_estaria_limpio(tmp_path):
    """Lo importante: no puede afirmar que no dispararía ninguna regla."""
    ctx = _ctx(tmp_path)
    msg = _mensaje(story=True)
    await scan_cmd._responder_scan(ctx, msg, msg, ctx.bot_data["cfg"], ctx.bot_data["db"])
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
    await scan_cmd._responder_scan(ctx, msg, msg, ctx.bot_data["cfg"], ctx.bot_data["db"])
    salida = msg.reply_text.await_args.args[0]
    assert "NO dispararía" in salida, f"perdió el veredicto normal: {salida!r}"
    assert "no lo he leído" not in salida


@pytest.mark.asyncio
async def test_si_se_puede_leer_la_historia_el_scan_la_analiza(tmp_path, monkeypatch):
    """Coherencia: si la moderación sabe leer historias, /scan también.

    Antes decía «no puedo analizarla» aunque Telethon sí pudiera, y el admin se
    quedaba sin saber qué habría hecho el bot con ese mensaje.
    """
    from src import story_reader
    from telegram import MessageEntity

    TEXTO = "Click to subscribe https://t.me/+67gOPOowkDliODQy"
    off = len(TEXTO[:TEXTO.index("https")].encode("utf-16-le")) // 2
    ents = [MessageEntity(type="url", offset=off, length=len(TEXTO) - off)]

    async def _falso_lector(_ctx, _story):
        return TEXTO, ents
    monkeypatch.setattr(story_reader, "leer_caption", _falso_lector)

    ctx = _ctx(tmp_path)
    msg = _mensaje(story=True)
    await scan_cmd._responder_scan(ctx, msg, msg, ctx.bot_data["cfg"], ctx.bot_data["db"])
    salida = msg.reply_text.await_args.args[0]

    assert "no lo he leído" not in salida, "dice que no pudo leerla habiéndola leído"
    assert "t.me" in salida, f"no muestra el texto recuperado: {salida!r}"


@pytest.mark.asyncio
async def test_si_no_se_puede_leer_sigue_avisando(tmp_path, monkeypatch):
    """Contrapeso: caducada o sin Telethon, el aviso honesto tiene que seguir."""
    from src import story_reader

    async def _no_lee(_ctx, _story):
        return None
    monkeypatch.setattr(story_reader, "leer_caption", _no_lee)

    ctx = _ctx(tmp_path)
    msg = _mensaje(story=True)
    await scan_cmd._responder_scan(ctx, msg, msg, ctx.bot_data["cfg"], ctx.bot_data["db"])
    salida = msg.reply_text.await_args.args[0]
    assert "no lo he leído" in salida


@pytest.mark.asyncio
async def test_el_scan_explica_que_pasaria_segun_quien_la_comparta(tmp_path, monkeypatch):
    """El /scan solo corre detectores de CONTENIDO, así que por sí solo no dice si
    banearía. Como la estructura depende de quién lo mande, se simulan los perfiles.
    """
    from src import story_reader
    from telegram import MessageEntity

    TEXTO = "Click to subscribe https://t.me/+67gOPOowkDliODQy"
    off = len(TEXTO[:TEXTO.index("https")].encode("utf-16-le")) // 2
    ents = [MessageEntity(type="url", offset=off, length=len(TEXTO) - off)]

    async def _lee(_ctx, _story):
        return TEXTO, ents
    monkeypatch.setattr(story_reader, "leer_caption", _lee)

    ctx = _ctx(tmp_path)
    msg = _mensaje(story=True)
    await scan_cmd._responder_scan(ctx, msg, msg, ctx.bot_data["cfg"], ctx.bot_data["db"])
    salida = msg.reply_text.await_args.args[0]

    assert "Recién llegado" in salida, "no explica el caso del recién llegado"
    assert "confianza" in salida, "no menciona qué pasa con un veterano"
    assert "Nada / Avisar / Banear" in salida, "no dice que al veterano se le pregunta"


@pytest.mark.asyncio
async def test_un_mensaje_normal_no_lleva_el_bloque_de_escenarios(tmp_path):
    """Solo tiene sentido en historias: en un mensaje normal sería ruido."""
    ctx = _ctx(tmp_path)
    msg = _mensaje(story=False, texto="hola, buenas tardes a todos")
    await scan_cmd._responder_scan(ctx, msg, msg, ctx.bot_data["cfg"], ctx.bot_data["db"])
    assert "Recién llegado" not in msg.reply_text.await_args.args[0]
