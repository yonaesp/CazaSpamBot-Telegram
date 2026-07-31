"""Detector: compartir una HISTORIA (story) recién entrado al grupo.

Este detector NO necesita Telethon. Trabaja solo con lo que da la Bot API, que de
una historia es lo mínimo: `chat` e `id`. Existe justamente por eso: el contenido
solo se puede leer por MTProto (`story_reader.py`), y quien instale el bot sin
cuenta secundaria se quedaría sin ninguna defensa ante este vector.

La señal no es «tiene una historia», que sería un falso positivo asegurado: es
**compartir la historia de OTRO chat nada más entrar, como primer mensaje**. Un
recién llegado que aún no ha hablado y lo primero que hace es plantar la historia
de un canal ajeno es el patrón de spam; compartir la propia es normal y no cuenta.

Reparto deliberado de puntos:
- **Primer mensaje** (con el join presenciado): 100, ban. Es el caso que se coló y
  no hay lectura posible que lo desmienta.
- **Recién entrado pero ya había hablado**: 40. Por sí solo NO banea, se queda en
  revisión. Si además se pudo leer el contenido y este dispara alguna regla, los
  scores se suman y sí se actúa: la estructura sospecha, el texto confirma.

Guarda imprescindible (la misma que `first_msg_media`): solo si el bot presenció
el JOIN. Sin `join_ts` no sabemos si es de verdad su primer mensaje, podría llevar
años en el grupo, y ese es el falso positivo conocido con usuarios anteriores al bot.
"""
from __future__ import annotations

from ..i18n import t
from . import Hit

# Misma ventana que `forward_first_msg`: «recién llegado» son los primeros 3 minutos.
VENTANA_RECIENTE_S = 180


def check(
    msg,
    user_id: int,
    is_first_msg: bool,
    bot_saw_join: bool,
    seconds_since_join: float | None = None,
) -> Hit:
    story = getattr(msg, "story", None)
    if story is None:
        return Hit.none()
    if not bot_saw_join:
        # Usuario anterior al bot: no sabemos qué es «su primer mensaje».
        return Hit.none()

    origen = getattr(story, "chat", None)
    origen_id = getattr(origen, "id", None)
    if origen_id is not None and origen_id == user_id:
        # Su propia historia. Es lo normal y no dice nada.
        return Hit.none()

    nombre = (getattr(origen, "title", None)
              or getattr(origen, "username", None)
              or str(origen_id or "?"))

    if is_first_msg:
        return Hit(
            rule="story_share",
            score=100,
            reason=t("reason.story_first", source=nombre),
            payload={"story_id": getattr(story, "id", None), "source_chat": origen_id},
        )

    if seconds_since_join is not None and seconds_since_join <= VENTANA_RECIENTE_S:
        return Hit(
            rule="story_share",
            score=40,
            reason=t("reason.story_recent", source=nombre),
            payload={"story_id": getattr(story, "id", None), "source_chat": origen_id},
        )

    return Hit.none()
