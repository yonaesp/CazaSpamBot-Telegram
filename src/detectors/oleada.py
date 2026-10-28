"""Detector: el mismo mensaje, en la misma hora, de varias cuentas NUEVAS distintas.

Es el hermano de `cross_post`. Aquel caza a UNA persona repartiendo el mismo
anuncio por varios grupos; este caza a VARIAS cuentas soltando el mismo texto, que
es como trabaja una red: cada cuenta escribe una vez y ninguna parece gran cosa por
separado. La idea viene de `tg-spam` (opción `--duplicates`), que la aplica a
cualquiera; aquí se acota más.

No mira el contenido, así que también caza una campaña nueva cuyo vocabulario no
está en ninguna lista. Por eso mismo no decide nunca sola.

## Anti falso positivo

- **Solo para quien está en sus primeros mensajes.** Que dos veteranos peguen la
  misma noticia o el mismo error de Windows es conversación normal.
- **Texto largo**: ≥ `MIN_CARACTERES` y ≥ `MIN_PALABRAS`. «Hola a todos» o
  «gracias» los repite medio grupo.
- **Casi calcado**: coseno de n-gramas ≥ `SIMILITUD`, el mismo del clasificador.
  Cambiar mayúsculas, emojis o una palabra no lo esquiva; escribir parecido sí.
- **Score `SCORE` (35), por debajo del mute (40)**: solo suma. Hace falta otra
  señal (un enlace, un @ externo, lo aprendido) para que pase algo.

Medido el 28-oct-2026: en toda la base solo había 1 primer mensaje repetido por
dos cuentas distintas (publicidad de apuestas en chino) y ya se había cazado por
otro lado. Es una red para lo que venga, no para algo que ya pase a menudo.
"""
from __future__ import annotations

import time

from .. import learning
from ..i18n import t
from . import Hit

MIN_CARACTERES = 40
MIN_PALABRAS = 6
VENTANA_S = 60 * 60
SIMILITUD = 0.9
SCORE = 35


def check(db, user_id: int, texto: str | None, is_first_msg: bool,
          ahora: float | None = None) -> Hit:
    """¿Otras cuentas acaban de escribir esto mismo?"""
    if not is_first_msg:
        return Hit.none()
    norm = learning.normalize(texto)
    if len(norm) < MIN_CARACTERES or len(norm.split()) < MIN_PALABRAS:
        return Hit.none()
    desde = (ahora if ahora is not None else time.time()) - VENTANA_S
    try:
        otros = db.textos_recientes_de_otros(user_id, desde)
    except Exception:  # noqa: BLE001 — una consulta no puede tumbar la moderación
        return Hit.none()
    cuentas = set()
    for uid, txt in otros:
        if uid in cuentas:
            continue
        sim, _ = learning.best_match(norm, [learning.normalize(txt)])
        if sim >= SIMILITUD:
            cuentas.add(uid)
    if not cuentas:
        return Hit.none()
    return Hit(
        rule="oleada",
        score=SCORE,
        reason=t("reason.oleada", n=len(cuentas) + 1),
        payload={"cuentas": len(cuentas) + 1, "window_s": VENTANA_S},
    )
