"""Leer el contenido de una HISTORIA (story) compartida en un grupo.

La Bot API entrega un objeto `Story` con SOLO `chat` e `id`: ni texto, ni imagen,
ni entidades, ni marca de reenvío. Un mensaje así llega a `on_message` totalmente
vacío, ningún detector de contenido tiene nada que mirar, y el spam pasa limpio.
Caso real: una historia con publicidad de cripto compartida en un grupo, con su
enlace de invitación bien visible para los humanos e invisible para el bot.

MTProto sí da el contenido: `stories.getStoriesByID(peer, [id])` devuelve un
`StoryItem` con `caption` y `entities`. Con eso el mensaje se puede evaluar con
los MISMOS detectores que cualquier otro, sin inventar heurísticas nuevas ni
subir el riesgo de falsos positivos: la evidencia es el texto real.

Dos cosas confirmadas en la documentación oficial antes de usarlo:

1. **No delata la cuenta.** `getStoriesByID` NO cuenta como visualización: las
   vistas solo se registran llamando aparte a `stories.incrementStoryViews`
   (https://core.telegram.org/api/stories). El autor de la historia no ve a la
   cuenta secundaria en su lista de espectadores, que es justo lo que hay que
   proteger.
2. **Caducan.** Una historia vive entre 6 y 48 horas (24 h lo normal). Pasado ese
   plazo solo la ve quien la publicó. Para moderar en vivo da igual, porque el
   spam llega con la historia recién puesta; para analizar a posteriori un mensaje
   viejo, ya no hay nada que leer.

Es best-effort de principio a fin: si Telethon no está, si el peer no se puede
resolver o si Telegram devuelve error, se devuelve None y el bot sigue como antes.
Nunca se propaga una excepción a la ruta de moderación.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("antispam")

# PTB procesa los updates de UNO EN UNO (la Application se construye sin
# `concurrent_updates`), así que cualquier espera aquí congela el bot entero: no se
# modera nada más, no entran joins. Y `get_input_entity` sobre un canal desconocido
# dispara `contacts.ResolveUsername`, de lo más propenso a FloodWait, ante el cual
# Telethon DUERME sola hasta 60 s sin lanzar excepción. Mismo tope que usa
# `detectors/photos_batch.py`, que ya se topó con esto.
_TIMEOUT_S = 5.0


class MensajeConTextoDeHistoria:
    """Envuelve el mensaje real y le añade el texto recuperado de la historia.

    Los detectores leen `msg.text or msg.caption`, así que basta con exponer ese
    texto como `caption`. TODO lo demás (message_id, chat, from_user, date...) se
    delega al mensaje de verdad: el bot tiene que seguir borrando y respondiendo
    al mensaje real del grupo, no a un objeto inventado.
    """

    __slots__ = ("_real", "caption", "caption_entities")

    def __init__(self, real, caption: str, entities=None):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "caption", caption)
        object.__setattr__(self, "caption_entities", entities or [])

    def __getattr__(self, nombre):
        # Sin esta guarda, si `_real` no está puesto (copy.copy, unpickle a medias)
        # la búsqueda de `_real` reentra aquí y revienta con RecursionError en vez
        # de con un AttributeError legible.
        if nombre == "_real":
            raise AttributeError(nombre)
        return getattr(self._real, nombre)


# Entidades de MTProto -> tipos de la Bot API. Los detectores de enlaces y menciones
# NO miran el texto plano, solo las entidades (`external_mention._extract_entities`,
# `url_blocklist`), así que sin esta traducción el texto se recuperaría a medias: se
# leería la publicidad pero no el enlace de invitación, que es la parte que importa.
# Los desplazamientos son en unidades UTF-16 en las dos APIs, así que valen tal cual.
_TIPOS = {
    "MessageEntityUrl": "url",
    "MessageEntityTextUrl": "text_link",
    "MessageEntityMention": "mention",
    "MessageEntityMentionName": "text_mention",
    "MessageEntityHashtag": "hashtag",
    "MessageEntityCashtag": "cashtag",
    "MessageEntityBotCommand": "bot_command",
    "MessageEntityEmail": "email",
    "MessageEntityPhone": "phone_number",
    "MessageEntityBold": "bold",
    "MessageEntityItalic": "italic",
    "MessageEntityUnderline": "underline",
    "MessageEntityStrike": "strikethrough",
    "MessageEntitySpoiler": "spoiler",
    "MessageEntityCode": "code",
    "MessageEntityPre": "pre",
    "MessageEntityBlockquote": "blockquote",
    "MessageEntityCustomEmoji": "custom_emoji",
}


def convertir_entidades(entidades) -> list:
    """Traduce las entidades de Telethon a `telegram.MessageEntity`.

    Lo que no se sabe traducir se descarta en silencio: es preferible perder un
    subrayado a que una entidad rara tumbe la moderación del mensaje.
    """
    from telegram import MessageEntity
    salida = []
    for ent in (entidades or []):
        tipo = _TIPOS.get(type(ent).__name__)
        if tipo is None:
            continue
        try:
            salida.append(MessageEntity(
                type=tipo,
                offset=ent.offset,
                length=ent.length,
                url=getattr(ent, "url", None),
            ))
        except Exception as exc:  # noqa: BLE001
            log.debug("story_reader: entidad %s no convertible: %s", tipo, exc)
    return salida


async def leer_caption(context, story) -> tuple[str, list] | None:
    """Texto de la historia y sus entidades, o None si no se puede obtener.

    `story` es el objeto de la Bot API: solo trae `chat` e `id`.
    """
    reporter = context.bot_data.get("reporter")
    client = reporter.get_client() if reporter else None
    if client is None:
        return None                      # sin Telethon el bot sigue igual que antes
    chat = getattr(story, "chat", None)
    if chat is None or getattr(story, "id", None) is None:
        return None

    try:
        from telethon.tl.functions.stories import GetStoriesByIDRequest
    except Exception:                    # noqa: BLE001 - Telethon es opcional
        return None

    # Resolver el peer. Se intenta primero por @username porque es lo único que
    # resuelve de forma fiable un canal que esta cuenta no conoce; el id pelado
    # solo funciona si Telethon ya lo tiene cacheado en su sesión.
    referencias = []
    uname = getattr(chat, "username", None)
    if uname:
        referencias.append(uname)
    referencias.append(chat.id)

    peer = None
    for ref in referencias:
        try:
            peer = await asyncio.wait_for(client.get_input_entity(ref), _TIMEOUT_S)
            break
        except Exception as exc:         # noqa: BLE001
            log.debug("story_reader: no se pudo resolver el peer %r: %s", ref, exc)
    if peer is None:
        log.info("story_reader: peer irresoluble para la historia %s de chat=%s",
                 story.id, chat.id)
        return None

    try:
        res = await asyncio.wait_for(
            client(GetStoriesByIDRequest(peer=peer, id=[story.id])), _TIMEOUT_S)
    except Exception as exc:             # noqa: BLE001
        # CHANNEL_PRIVATE, STORIES_NEVER_CREATED, PEER_ID_INVALID, caducada...
        log.info("story_reader: Telegram no devolvió la historia %s: %s", story.id, exc)
        return None

    items = list(getattr(res, "stories", None) or [])
    if not items:
        return None
    caption = getattr(items[0], "caption", None)
    if not caption or not caption.strip():
        return None
    ents = convertir_entidades(getattr(items[0], "entities", None))
    log.info("story_reader: historia %s de chat=%s leída (%d chars, %d entidades)",
             story.id, chat.id, len(caption), len(ents))
    return caption, ents
