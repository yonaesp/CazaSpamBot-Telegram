"""Detector: usuario que envía un mensaje con botones inline (reply_markup).

Los usuarios normales NO pueden enviar mensajes con `reply_markup` (teclados
inline). Solo bots y canales. Cuando un usuario reenvía un mensaje de un canal
que tenía botones inline, esos botones se PRESERVAN en el forward.

Por tanto, encontrar `msg.reply_markup` en un mensaje cuyo `from_user` es un
usuario humano (no bot) es señal casi inequívoca de:
  a) Forward desde canal/bot promocional.
  b) Mensaje del propio user creado vía bot externo (raro en grupos normales).

Score alto pero NO inmediato 100 para permitir trust score (veteranos que
ocasionalmente reenvían algo de un canal legítimo no se banean).
"""
from __future__ import annotations

from telegram import Message

from . import Hit


def check(msg: Message) -> Hit:
    rm = getattr(msg, "reply_markup", None)
    if rm is None:
        return Hit.none()
    keyboard = getattr(rm, "inline_keyboard", None) or []
    n_buttons = sum(len(row) for row in keyboard)
    if n_buttons == 0:
        return Hit.none()

    # Recopilar URLs de los botones para el log/quip (algunos botones tienen url, otros callback_data)
    urls: list[str] = []
    for row in keyboard:
        for btn in row:
            url = getattr(btn, "url", None)
            if url:
                urls.append(url)

    score = 90  # alto pero no max, para que el trust score pueda degradar
    reasons = [f"mensaje con {n_buttons} botones inline (los users normales no pueden enviarlos)"]
    if urls:
        reasons.append(f"botones llevan a {len(urls)} URLs")
    return Hit(
        rule="inline_buttons_from_user",
        score=score,
        reason=" + ".join(reasons),
        payload={
            "n_buttons": n_buttons,
            "urls": urls[:5],
        },
    )
