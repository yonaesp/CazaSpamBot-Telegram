"""Historias compartidas en un grupo: el bot pide el texto real por MTProto.

La Bot API entrega la historia VACÍA (solo `chat` e `id`), así que el mensaje
llegaba a la moderación sin nada que analizar y el spam pasaba limpio. Caso real:
una historia con publicidad de cripto y su enlace de invitación, visible para
cualquier humano del grupo e invisible para los 21 detectores.

Aquí se comprueba que, recuperado el texto, los detectores de siempre lo cazan, y
que cuando NO se puede recuperar el bot se queda como estaba en vez de romperse.
"""
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import story_reader

TEXTO_REAL = (
    "👀Recently I came across a private group of a legendary whale. "
    "I tested his predictions and was able to significantly increase my budget! "
    "‼️Many subscribers have already earned thousands of dollars, only 100 spots left"
    "📎Click to subscribe ⬇️https://t.me/+67gOPOowkDliODQy"
)


def _story(chat_id=-100123, username=None, sid=7):
    return types.SimpleNamespace(
        id=sid, chat=types.SimpleNamespace(id=chat_id, username=username, type="channel"),
    )


def _ctx(client=None):
    ctx = MagicMock()
    reporter = MagicMock()
    reporter.get_client.return_value = client
    ctx.bot_data = {"reporter": reporter}
    return ctx


def _cliente(caption=TEXTO_REAL, falla_peer=False, falla_request=False):
    client = MagicMock()
    if falla_peer:
        client.get_input_entity = AsyncMock(side_effect=RuntimeError("PEER_ID_INVALID"))
    else:
        client.get_input_entity = AsyncMock(return_value="peer")
    if falla_request:
        client.side_effect = RuntimeError("CHANNEL_PRIVATE")
    else:
        item = types.SimpleNamespace(caption=caption, entities=[])
        client.return_value = types.SimpleNamespace(stories=[item] if caption is not None else [])
    # el cliente se invoca como client(Request(...)) -> corrutina
    real = client.side_effect or client.return_value

    async def _llamada(_req):
        if isinstance(real, Exception):
            raise real
        return real
    client.side_effect = _llamada
    return client


@pytest.mark.asyncio
async def test_recupera_el_texto_de_la_historia():
    res = await story_reader.leer_caption(_ctx(_cliente()), _story())
    assert res is not None, 'no recuperó la historia'
    cap, _ents = res
    assert cap == TEXTO_REAL


@pytest.mark.asyncio
async def test_sin_telethon_no_revienta():
    """Quien instale el bot sin cuenta secundaria debe seguir funcionando."""
    assert await story_reader.leer_caption(_ctx(None), _story()) is None


@pytest.mark.asyncio
async def test_peer_irresoluble_devuelve_none():
    """Un canal privado que esta cuenta no conoce: no se puede resolver."""
    assert await story_reader.leer_caption(_ctx(_cliente(falla_peer=True)), _story()) is None


@pytest.mark.asyncio
async def test_error_de_telegram_no_se_propaga():
    """CHANNEL_PRIVATE, STORIES_NEVER_CREATED, historia caducada... nunca deben
    tumbar la moderación del mensaje."""
    assert await story_reader.leer_caption(_ctx(_cliente(falla_request=True)), _story()) is None


@pytest.mark.asyncio
async def test_historia_sin_texto_devuelve_none():
    assert await story_reader.leer_caption(_ctx(_cliente(caption="   ")), _story()) is None


def test_el_envoltorio_delega_todo_menos_el_texto():
    """Borrar y responder tienen que seguir apuntando al mensaje REAL del grupo."""
    real = types.SimpleNamespace(message_id=555, chat_id=-100999, text=None,
                                 caption=None, entities=None, photo=None)
    shim = story_reader.MensajeConTextoDeHistoria(real, TEXTO_REAL)
    assert shim.caption == TEXTO_REAL
    assert shim.message_id == 555, "perdió el id del mensaje real: borraría el que no es"
    assert shim.chat_id == -100999
    assert shim.text is None, "los detectores hacen `text or caption`; text debe seguir vacío"


def _con_entidades(texto, url):
    """Monta el mensaje como lo entrega Telegram: con la URL en una entidad.

    Importa de verdad: los detectores de enlaces NO miran el texto plano, solo las
    entidades. Sin traducirlas se recupera la publicidad pero se pierde el enlace
    de invitación, que es la prueba.
    """
    from telegram import MessageEntity
    off = len(texto[:texto.index(url)].encode("utf-16-le")) // 2   # offsets UTF-16
    ents = [MessageEntity(type="url", offset=off, length=len(url))]
    real = types.SimpleNamespace(text=None, caption=None, entities=None,
                                 caption_entities=None, photo=None)
    return story_reader.MensajeConTextoDeHistoria(real, texto, ents)


def test_el_spam_real_se_caza_con_el_texto_recuperado():
    """El caso que se coló en el grupo, de punta a punta."""
    from src.detectors import external_mention as ext

    shim = _con_entidades(TEXTO_REAL, "https://t.me/+67gOPOowkDliODQy")
    h = ext.check(shim, chat_id=-100999, is_first_msg=True, detect_user_mentions=True,
                  detect_tg_links=True, is_user_in_chat=lambda *a, **k: False,
                  resolve_username=lambda *a, **k: None, own_chat_username=None)
    assert h, "con el texto recuperado no saltó ninguna regla: el arreglo no sirve"
    assert h.score >= 100, f"score insuficiente para actuar: {h.score}"


def test_sin_traducir_las_entidades_el_enlace_se_pierde():
    """Fija por qué existe `convertir_entidades`: sin ella el arreglo se queda a medias.

    Se recupera el texto (y con él la publicidad), pero el enlace de invitación
    (la prueba de verdad) es invisible, porque vive en las entidades.
    """
    from src.detectors import external_mention as ext

    real = types.SimpleNamespace(text=None, caption=None, entities=None,
                                 caption_entities=None, photo=None)
    sin_ents = story_reader.MensajeConTextoDeHistoria(real, TEXTO_REAL)   # entidades vacías
    h = ext.check(sin_ents, chat_id=-100999, is_first_msg=True, detect_user_mentions=True,
                  detect_tg_links=True, is_user_in_chat=lambda *a, **k: False,
                  resolve_username=lambda *a, **k: None, own_chat_username=None)
    assert not h, "si esto empieza a disparar, `convertir_entidades` ya no hace falta"


def test_convertir_entidades_traduce_los_tipos_que_importan():
    class _Ent:
        def __init__(self, nombre, off, ln, url=None):
            self.offset, self.length = off, ln
            if url:
                self.url = url
            self.__class__ = type(nombre, (_Ent,), {})

    ents = story_reader.convertir_entidades([
        _Ent("MessageEntityUrl", 0, 10),
        _Ent("MessageEntityTextUrl", 20, 5, url="https://spam.example"),
        _Ent("MessageEntityMention", 30, 8),
        _Ent("MessageEntityDesconocidaDelFuturo", 40, 3),   # se descarta sin romper
    ])
    tipos = [e.type for e in ents]
    assert tipos == ["url", "text_link", "mention"], tipos
    assert ents[1].url == "https://spam.example", "se perdió la URL oculta del text_link"
