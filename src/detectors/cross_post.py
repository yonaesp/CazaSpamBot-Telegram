"""Detector: el mismo mensaje, a la vez, en varios de nuestros grupos.

Aprovecha algo que casi ningún bot tiene y este sí: la **federación**. Cuando
moderas cuatro grupos a la vez ves una cosa que quien modera uno solo no puede ver.

Una persona escribe en el grupo donde tiene el problema. Un anuncio se reparte por
todos. Que el MISMO texto aparezca en tres de cuatro grupos en cuestión de minutos
no es una coincidencia: es una campaña, y da igual lo bien escrito que esté el
mensaje o lo limpia que esté la cuenta.

Lo bueno de esta señal es que **no mira el contenido**. Un anuncio de spam nuevo,
en un idioma que no tenemos en las listas, con vocabulario que nadie ha visto
todavía, sigue siendo el mismo texto repetido. Por eso caza lo que las listas
negras todavía no saben cazar.

## Anti falso positivo

Hay motivos legítimos para repetirse, y por eso:

- **Solo cuenta a la MISMA persona.** Dos usuarios distintos diciendo «buenos
  días» no es nada.
- **Solo cuenta en chats DISTINTOS.** Repetirse en el mismo grupo es pesadez o un
  fallo de red, y de eso ya se ocupa el antiflood.
- **Ventana corta.** Preguntar lo mismo en dos grupos con una semana de diferencia
  es razonable; hacerlo en diez minutos, no.
- **Textos cortos fuera.** «gracias», «sí», «alguien?», un emoji: se repiten solos
  todo el tiempo y no prueban nada. Por debajo de `MIN_CARACTERES` no se mira.
- **Se compara el texto NORMALIZADO** (el mismo `learning.normalize` que usa el
  clasificador), así que cambiar mayúsculas o meter caracteres invisibles no
  sirve para esquivarlo.
- **Hacen falta tres chats, no dos.** Con dos era demasiado fácil: alguien con un
  problema de verdad lo pregunta en el de Windows 10 y en el de Windows 11, que se
  parecen. Tres ya es reparto.

Ninguna señal decide sola, como siempre: el score es alto pero no llega a ban por
sí mismo, así que hace falta que algo más lo acompañe o que el trust sea bajo.
"""
from __future__ import annotations

import time

from ..i18n import t
from . import Hit

# Por debajo de esto no se mira: los mensajes cortos se repiten solos.
MIN_CARACTERES = 25
# En cuánto tiempo. Corto a propósito: la señal es la simultaneidad.
VENTANA_S = 15 * 60
# Cuántos chats DISTINTOS hacen falta.
MIN_CHATS = 3

SCORE = 85


def check(db, chat_id: int, user_id: int, texto_normalizado: str,
          ahora: float | None = None) -> Hit:
    """¿Esta persona acaba de escribir esto mismo en otros grupos nuestros?"""
    if not texto_normalizado or len(texto_normalizado) < MIN_CARACTERES:
        return Hit.none()
    try:
        chats = db.chats_con_el_mismo_texto(
            user_id, texto_normalizado,
            desde_ts=(ahora if ahora is not None else time.time()) - VENTANA_S,
        )
    except Exception:  # noqa: BLE001 — una consulta no puede tumbar la moderación
        return Hit.none()
    otros = [c for c in chats if c != chat_id]
    if len(otros) + 1 < MIN_CHATS:
        return Hit.none()
    return Hit(
        rule="cross_post",
        score=SCORE,
        reason=t("reason.cross_post", n=len(otros) + 1),
        payload={"chats": len(otros) + 1, "window_s": VENTANA_S},
    )
