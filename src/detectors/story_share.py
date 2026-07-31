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
from ..wordlists import load_and_compile
from . import Hit

# Misma ventana que `forward_first_msg`: «recién llegado» son los primeros 3 minutos.
VENTANA_RECIENTE_S = 180

# Por debajo de esto se considera que alguien «apenas escribe» en el grupo: lleva
# tiempo dentro pero no participa. Es el perfil que de repente planta una historia
# de spam, y el que el usuario pidió distinguir del veterano que sí habla.
POCO_ACTIVO_MAX_MSGS = 5

# Nombres de canal típicos de este spam. Editable en config/blacklist/story_source.txt
# (y ampliable desde el panel). Se contrasta contra el título y el @username del
# canal de origen, que es lo ÚNICO que la Bot API entrega siempre: el contenido
# solo se lee por Telethon y solo mientras la historia sigue viva.
# TODOS llevan \b a proposito. Con coincidencia por subcadena, «rich» casaba dentro
# de «Zürich Nachrichten», «Heinrich Böll» o «Ostrich Fans», y «pump» dentro de
# «Pumpkin Recipes»: ban federado a un usuario legítimo por el nombre de un canal
# de noticias suizo. El peligro no era el término, era la falta de límites.
_FUENTE_DEFAULTS = [
    r"\bsignals?\b", r"\bcrypto", r"\bbitcoin\b", r"\bbtc\b", r"\bbinance\b",
    r"\bforex\b", r"\bairdrop", r"\bpump\b", r"\bwhale\b", r"\binsider\b",
    r"\bprofits?\b", r"\bearn(ings)?\b", r"\bmillionaire\b", r"\brich\b",
    r"\bcasino\b", r"\bjackpot\b", r"\bbetting\b", r"\bonlyfans\b", r"\b18\+",
    r"\bxxx\b", r"\bescorts?\b",
]


def _fuente_sospechosa(nombre: str, username: str | None) -> bool:
    rx = load_and_compile("story_source.txt", _FUENTE_DEFAULTS, boundaries=False)
    # El guion bajo ES carácter de palabra, así que en `btc_signals_vip` el `\b` de
    # `\bsignals\b` no casa y el término se escaparía. Y los @username de Telegram
    # van llenos de guiones bajos, que es justo donde vive el nombre del canal.
    # Se tratan como separadores, que es lo que son a efectos de leerlo.
    limpio = (username or "").replace("_", " ").replace(".", " ")
    return bool(rx.search(nombre or "") or rx.search(limpio))


def check(
    msg,
    user_id: int,
    is_first_msg: bool,
    bot_saw_join: bool,
    seconds_since_join: float | None = None,
    msg_count: int | None = None,
) -> Hit:
    story = getattr(msg, "story", None)
    if story is None:
        return Hit.none()

    origen = getattr(story, "chat", None)
    origen_id = getattr(origen, "id", None)
    if origen_id is not None and origen_id == user_id:
        # Su propia historia. Es lo normal y no dice nada.
        return Hit.none()

    titulo = getattr(origen, "title", None)
    uname = getattr(origen, "username", None)
    nombre = titulo or uname or str(origen_id or "?")
    datos = {"story_id": getattr(story, "id", None), "source_chat": origen_id}

    # 1) Estructura: recién llegado. Exige join presenciado, porque sin `join_ts` no
    #    sabemos si es de verdad su primer mensaje (podría llevar años en el grupo).
    if bot_saw_join:
        if is_first_msg:
            return Hit(rule="story_share", score=100,
                       reason=t("reason.story_first", source=nombre), payload=datos)
        if seconds_since_join is not None and seconds_since_join <= VENTANA_RECIENTE_S:
            return Hit(rule="story_share", score=40,
                       reason=t("reason.story_recent", source=nombre), payload=datos)

    # 2) El canal de origen tiene pinta de spam. Esta señal NO necesita join
    #    presenciado: la evidencia es el nombre del canal, no cuándo entró. Cubre
    #    justo al que lleva tiempo en el grupo y apenas escribe.
    if _fuente_sospechosa(titulo or "", uname):
        apenas_escribe = msg_count is not None and msg_count < POCO_ACTIVO_MAX_MSGS
        if apenas_escribe:
            return Hit(rule="story_share", score=100,
                       reason=t("reason.story_source_quiet", source=nombre,
                                n=msg_count), payload=datos)
        # Participa de verdad: el nombre por sí solo NO le banea. Suma y que decidan
        # el resto de señales y el trust, que para eso está.
        return Hit(rule="story_share", score=40,
                   reason=t("reason.story_source", source=nombre), payload=datos)

    return Hit.none()
