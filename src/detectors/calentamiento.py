"""Detector: «calentar» la cuenta con mensajes vacíos y luego soltar el enlace.

Un bot de spam sabe que el primer mensaje se mira con lupa (`FIRST_MSG_WINDOW`,
3 mensajes). Así que algunos gastan esos mensajes en nada («ok», «hi», «jaja»,
una pregunta vaga) y el @ o el enlace llega después, cuando ya puntúa la mitad. Lo
cuentan `tg-spam` (`--max-short-msg-count`) y varios moderadores; aquí no se había
medido, así que esto es una red prudente y no una regla probada.

## Cuándo suma

Todo a la vez:
- Ya ha salido de la ventana de primeros mensajes (si no, ya se le mira con lupa).
- Entró hace ≤ `DIAS_RECIEN_LLEGADO` días (el bot vio la entrada) y lleva
  ≤ `MAX_MENSAJES` mensajes.
- Este mensaje ya trae un @ externo o un enlace a Telegram de fuera
  (`external_mention_or_link`). Sin eso no pasa nada: hablar poco no es delito.
- Todo lo que escribió antes, en las últimas 24 h, son ≥ `MIN_PREVIOS` mensajes de
  ≤ `MAX_PALABRAS` palabras.

Suma `SCORE` (25) al enlace. No decide sola; un perfil con confianza ≥ 70 no se
toca, y entre 40 y 69 una acción severa va a revisión del admin.
"""
from __future__ import annotations

import time

from ..i18n import t
from . import Hit

DIAS_RECIEN_LLEGADO = 7
MAX_MENSAJES = 8
MIN_PREVIOS = 2
MAX_PALABRAS = 3
VENTANA_S = 24 * 3600
SCORE = 25


def check(db, chat_id: int, user_id: int, msg_id: int, msg_count: int,
          is_first_msg: bool, hay_enlace_externo: bool,
          ahora: float | None = None) -> Hit:
    """¿Mensajes vacíos primero y ahora el @ o el enlace?"""
    if is_first_msg or not hay_enlace_externo or msg_count > MAX_MENSAJES:
        return Hit.none()
    ahora = ahora if ahora is not None else time.time()
    try:
        seen = db.get_seen(chat_id, user_id)
        join_ts = seen["join_ts"] if seen else None
        if not join_ts or ahora - float(join_ts) > DIAS_RECIEN_LLEGADO * 86400:
            return Hit.none()
        previos = db.textos_previos(chat_id, user_id, msg_id, ahora - VENTANA_S)
    except Exception:  # noqa: BLE001 — una consulta no puede tumbar la moderación
        return Hit.none()
    if len(previos) < MIN_PREVIOS:
        return Hit.none()
    if any(len((p or "").split()) > MAX_PALABRAS for p in previos):
        return Hit.none()
    return Hit(
        rule="calentamiento",
        score=SCORE,
        reason=t("reason.calentamiento", n=len(previos)),
        payload={"previos": len(previos)},
    )
