"""Entradas en avalancha: mirar el GRUPO, no a cada uno por separado.

Todo lo demás en este bot razona persona a persona: tu perfil, tu bio, tu primer
mensaje, tu confianza. Contra una **raid** eso no vale, porque el ataque no está en
ninguna cuenta sino en el conjunto: quince cuentas que por separado parecen del
montón (nombre latino, sin nada raro, cuenta nueva pero no recién creada) entrando
en dos minutos. Cada una pasa el filtro. Todas juntas son un asalto.

## Qué se hace, y sobre todo qué NO

Lo tentador es cerrar el grupo o silenciar a todo el que entre. Se ha descartado:
castiga a los legítimos que pasaban por ahí y convierte un ataque en una caída de
servicio del grupo, que es justo lo que buscaba quien ataca.

En vez de eso, durante unos minutos el chat entra en **alerta** y lo único que
cambia es que **la duda deja de resolverse a favor del que entra**:

- Los que llegan mientras dura la alerta quedan marcados, y su primer mensaje se
  evalúa como si fuera el de alguien sospechoso: es `handlers` quien lo usa.
- No se banea a nadie por haber entrado. Entrar no es una infracción, y en una
  raid siempre hay gente normal que entró en ese minuto por casualidad.
- Se avisa al admin UNA vez por episodio, con el número de entradas y el plazo.

## Por qué la ventana es corta y el umbral alto

Un grupo que crece de verdad (una mención en otro sitio, un vídeo) puede recibir
muchas entradas seguidas. Lo que distingue una raid no es el volumen sino la
CONCENTRACIÓN. El umbral no se eligió a ojo: sobre las **881 entradas** que hay
registradas en estos grupos, el máximo histórico en una ventana de 60 s es **2**
(y **3** en una de 300 s). Con 6 hay un margen de tres veces sobre lo que ha
pasado nunca, así que un crecimiento orgánico no lo toca. Son ajustables por si un
grupo mucho más grande necesita otra cosa.

La cuenta se lleva en memoria. Perderla al reiniciar es aceptable: una alerta dura
minutos, no días, y no vale la pena una tabla para eso.
"""
from __future__ import annotations

import logging
import time
from collections import deque

from telegram.error import TelegramError

from .i18n import t

log = logging.getLogger(__name__)

# Cuántas entradas, en cuántos segundos, para considerarlo una avalancha.
UMBRAL_ENTRADAS = 6
VENTANA_S = 60
# Cuánto dura la desconfianza después. Corto: es una tormenta, no un castigo.
ALERTA_S = 15 * 60
# Cada cuánto, como mucho, se avisa al admin del mismo chat.
AVISO_CADA_S = 30 * 60

_CLAVE = "_antiraid"


def _estado(context) -> dict:
    return context.bot_data.setdefault(_CLAVE, {"entradas": {}, "alerta": {}, "avisado": {}})


def registrar_entrada(context, chat_id: int, cuando: float | None = None) -> bool:
    """Apunta una entrada. Devuelve True si con esta se cruza el umbral.

    Solo devuelve True en el momento del cruce, no mientras dure la alerta: así
    quien llama puede avisar una vez y no en cada entrada de la avalancha.
    """
    ahora = cuando if cuando is not None else time.time()
    st = _estado(context)
    cola = st["entradas"].setdefault(chat_id, deque(maxlen=200))
    cola.append(ahora)
    while cola and cola[0] < ahora - VENTANA_S:
        cola.popleft()
    if len(cola) < UMBRAL_ENTRADAS:
        return False
    ya_estaba = en_alerta(context, chat_id, ahora)
    st["alerta"][chat_id] = ahora + ALERTA_S
    return not ya_estaba


def en_alerta(context, chat_id: int, ahora: float | None = None) -> bool:
    """¿Este chat está ahora mismo en medio de una avalancha de entradas?"""
    st = context.bot_data.get(_CLAVE)
    if not st:
        return False
    hasta = st["alerta"].get(chat_id)
    if hasta is None:
        return False
    if (ahora if ahora is not None else time.time()) > hasta:
        del st["alerta"][chat_id]
        return False
    return True


def entradas_en_ventana(context, chat_id: int) -> int:
    st = context.bot_data.get(_CLAVE)
    if not st:
        return 0
    return len(st["entradas"].get(chat_id, ()))


def limpiar(context) -> None:
    """Olvida todo (tests)."""
    context.bot_data.pop(_CLAVE, None)


async def avisar(context, cfg, chat_id: int, chat_title: str | None) -> None:
    """Un aviso por episodio y por chat. Nunca en el grupo: solo al admin.

    En público sería contraproducente por partida doble: le confirma a quien ataca
    que ha funcionado, y alarma a los miembros por algo que el bot ya está tratando.
    """
    destino = getattr(cfg, "admin_notify_chat_id", None)
    if not destino:
        return
    st = _estado(context)
    ahora = time.time()
    if ahora - st["avisado"].get(chat_id, 0.0) < AVISO_CADA_S:
        return
    st["avisado"][chat_id] = ahora
    import html as _h
    try:
        await context.bot.send_message(
            chat_id=destino,
            text=t("antiraid.aviso",
                   chat=_h.escape(str(chat_title or chat_id)),
                   n=entradas_en_ventana(context, chat_id),
                   ventana=VENTANA_S,
                   minutos=ALERTA_S // 60),
            parse_mode="HTML",
        )
    except TelegramError as exc:
        log.warning("antiraid: no se pudo avisar: %s", exc)


# Cuánto se baja cada umbral mientras dura la alerta, y solo para quien entró EN
# ella. No es una acción nueva: es la misma escala de siempre, un peldaño más
# abajo. Un recién llegado que escribe «hola» sigue puntuando cero, porque los
# umbrales solo importan cuando ya hay señales.
REBAJA = {"ban": 20, "kick": 15, "mute": 5}


def entro_en_la_avalancha(context, chat_id: int, join_ts: float | None) -> bool:
    """¿Esta persona es de las que llegaron con la avalancha?

    Distinguirlo importa: en una raid también hay gente normal que ya estaba en el
    grupo hablando, y a esa no se le puede cambiar la vara de medir por algo que
    han hecho otros.
    """
    if join_ts is None or not en_alerta(context, chat_id):
        return False
    return (time.time() - float(join_ts)) <= (ALERTA_S + VENTANA_S)


def umbrales(context, cfg, chat_id: int, join_ts: float | None) -> tuple[int, int, int]:
    """(ban, kick, mute) para este usuario en este momento."""
    base = (cfg.ban_score, cfg.kick_score, cfg.mute_score)
    if not entro_en_la_avalancha(context, chat_id, join_ts):
        return base
    ban, kick, mute = base
    return (max(1, ban - REBAJA["ban"]),
            max(1, kick - REBAJA["kick"]),
            max(1, mute - REBAJA["mute"]))
