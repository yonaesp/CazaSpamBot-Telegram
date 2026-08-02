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
    # OJO: estos son el respaldo si falta config/blacklist/story_source.txt, y el
    # Dockerfile NO copia config/ (aquí llega por bind-mount). Un `docker run` de la
    # imagen pelada se queda con ESTA lista, así que tiene que cumplir la misma regla
    # de oro que el fichero: PAREJAS, nunca palabras sueltas. Cuando eran sueltas,
    # «insider» casaba con «Windows Insider Program» y «pump» con «Heat Pump UK».
    r"\b(?:crypto|bitcoin|btc|forex|binary|vip|free|premium|daily|group|club|insider|private)[\s_-]+signals?\b",
    r"\bsignals?[\s_-]+(?:vip|group|club|channel|premium|free|pro|insider)\b",
    r"\binsider[\s_-]+(?:signals?|trading|tips?|club|vip|profits?)\b",
    r"\b(?:crypto|bitcoin|btc|forex|binance)[\s_-]+(?:pump|profits?|invest|millionaire|vip)\b",
    r"\bpump[\s_-]*(?:&|and|/|n)?[\s_-]*dump\b",
    r"\bairdrop[\s_-]+(?:free|claim|bonus|token|nft|\d)",
    r"\bfree[\s_-]+airdrop\b",
    r"\bwhale[\s_-]+(?:signals?|alerts?|club|vip|trades?)\b",
    r"\b(?:daily|guaranteed|easy|fast|quick)[\s_-]+profits?\b",
    r"\bget[\s_-]+rich\b",
    r"\brich[\s_-]+(?:quick|fast)\b",
    r"\b(?:online|free|live)[\s_-]+casino\b",
    r"\bcasino[\s_-]+(?:online|bonus|free|slots?|jackpot|777)\b",
    r"\bonlyfans\b",
    r"\bescorts?[\s_-]+(?:service|girls?|vip|24h|agency)\b",
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
    if origen is None:
        # La Bot API siempre manda `chat`, pero sin él no hay nada que evaluar y no
        # se va a puntuar a ciegas.
        return Hit.none()
    origen_id = getattr(origen, "id", None)
    if origen_id is not None and origen_id == user_id:
        # Su propia historia. Es lo normal y no dice nada.
        return Hit.none()

    titulo = getattr(origen, "title", None)
    uname = getattr(origen, "username", None)
    nombre = titulo or uname or str(origen_id or "?")
    datos = {"story_id": getattr(story, "id", None), "source_chat": origen_id}

    # Se ACUMULA, no se retorna en la primera coincidencia. Retornando, la rama de
    # «recién llegado» (más leve) tapaba la del canal sospechoso (más grave) y salía
    # el score invertido: el recién llegado con un canal de spam puntuaba 40 y el
    # veterano con el mismo canal, 100. Justo al revés de lo que se pretende.
    score = 0
    motivos: list[str] = []

    # 1) Estructura: recién llegado. Exige join presenciado, porque sin `join_ts` no
    #    sabemos si es de verdad su primer mensaje (podría llevar años en el grupo).
    #    Vale POCO a propósito: por debajo de MUTE_SCORE, así que por sí sola no
    #    hace nada. Compartir una historia al entrar es raro, pero no es delito, y
    #    puede ser el canal enlazado del propio grupo.
    if bot_saw_join:
        if is_first_msg:
            score += 30
            motivos.append(t("reason.story_first", source=nombre))
        elif seconds_since_join is not None and seconds_since_join <= VENTANA_RECIENTE_S:
            score += 20
            motivos.append(t("reason.story_recent", source=nombre))

    # 2) El canal de origen tiene nombre de spam. NO necesita join presenciado: la
    #    evidencia es el nombre, no cuándo entró. Cubre al que lleva tiempo en el
    #    grupo y apenas escribe. La lista es de PAREJAS, nunca palabras sueltas
    #    («insider» solo cazaba «Windows Insider Program»).
    if _fuente_sospechosa(titulo or "", uname):
        if msg_count is not None and msg_count < POCO_ACTIVO_MAX_MSGS:
            score += 70
            motivos.append(t("reason.story_source_quiet", source=nombre, n=msg_count))
        else:
            # Participa de verdad: el nombre por sí solo no le toca. Suma y deciden
            # el resto de señales y el trust, que para eso está.
            score += 30
            motivos.append(t("reason.story_source", source=nombre))

    if not motivos:
        return Hit.none()
    return Hit(rule="story_share", score=score, reason=" + ".join(motivos), payload=datos)
