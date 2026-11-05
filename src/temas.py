"""Grupos con temas (foros): lo que cambia para el bot.

Un supergrupo con temas («categorías», como las de Domótica/Alexa y Windows 11) es
un solo chat con varios hilos. Tres cosas que el bot daba por hechas y no lo son:

1. **La respuesta.** Dentro de un tema, la Bot API pone en `reply_to_message` el
   mensaje que CREÓ el tema (`forum_topic_created`) aunque nadie haya respondido a
   nada. Leído a pelo, un `/warn` o un `/ban` sin responder irían contra quien abrió
   el tema, y todo mensaje parecería una respuesta. `respuesta()` devuelve solo la
   respuesta de verdad, y nadie más en `src/` lee `reply_to_message` (hay test).
2. **El hilo.** `message_thread_id` también existe en un grupo normal (identifica una
   cadena de respuestas), así que solo significa «tema» con `is_topic_message`
   (PTB lo advierte en `Message._parse_message_thread_id`). `hilo()` lo resuelve; lo
   que el bot publica a raíz de un mensaje va a ese tema, no a General.
3. **El orden.** Los `message_id` son del grupo entero, no de cada tema: el «mensaje
   anterior» a uno de General puede estar en otro tema. Caso real (5-nov-2026,
   Domótica/Alexa): un `@admin` sin responder en General hizo que el aviso enlazara
   un mensaje de otro tema del propio avisador, y no el spam que tenía justo encima.
   `tema_mtproto()` dice a qué tema pertenece un mensaje leído con la cuenta
   secundaria, para buscar el anterior DEL MISMO tema.
"""
from __future__ import annotations

from telegram import ForumTopicCreated

GENERAL = 1  # el tema General: en MTProto, los mensajes sin `forum_topic`


def es_tema(msg) -> bool:
    """True si el mensaje está en un tema que no es General.

    `is True` y no `bool()`: la Bot API da True o nada, y un doble de test con
    atributos automáticos no puede colar un tema que no existe.
    """
    return getattr(msg, "is_topic_message", None) is True


def hilo(msg) -> int | None:
    """El tema del mensaje para publicar en él (`message_thread_id`), o None (General)."""
    return getattr(msg, "message_thread_id", None) if es_tema(msg) else None


def respuesta(msg):
    """El mensaje al que responde de verdad, o None.

    Descarta la «respuesta» que la Bot API pone a todo mensaje de un tema: la del
    mensaje que lo creó.
    """
    r = getattr(msg, "reply_to_message", None)
    if r is None:
        return None
    if isinstance(getattr(r, "forum_topic_created", None), ForumTopicCreated):
        return None
    if es_tema(msg) and getattr(r, "message_id", None) == getattr(msg, "message_thread_id", None):
        return None
    return r


def tema_bot_api(msg) -> int:
    """Tema de un mensaje de la Bot API, con General = 1."""
    return hilo(msg) or GENERAL


def tema_mtproto(m) -> int:
    """Tema de un mensaje leído con Telethon, con General = 1.

    Un mensaje de un tema lleva `reply_to.forum_topic`; si además responde a otro, el
    tema va en `reply_to_top_id`, y si no, en `reply_to_msg_id`.
    """
    rt = getattr(m, "reply_to", None)
    if rt is None or not getattr(rt, "forum_topic", False):
        return GENERAL
    return getattr(rt, "reply_to_top_id", None) or getattr(rt, "reply_to_msg_id", None) or GENERAL
