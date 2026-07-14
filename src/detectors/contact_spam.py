"""Detector: CONTACTO compartido cuyo nombre/vCard es un reclamo de spam.

Vector muy común (apuestas/lotería china, escorts, promos): en vez de escribir el
anuncio como texto, el spammer COMPARTE UN CONTACTO cuyo `first_name`/`last_name`
es el reclamo (p.ej. «赛车.六合彩.PC28») y el `phone_number` es el WhatsApp/Telegram
de contacto. Como el texto va en `msg.contact` (no en `msg.text`/`caption`), los
detectores de texto no lo ven: hay que mirar dentro del contacto.

La tarjeta muestra los botones NATIVOS de Telegram (Mensaje / Añadir), que NO son
botones inline del remitente, así que `inline_buttons` tampoco dispara. De ahí el
hueco que cubre este detector.

Señales (cualquiera dispara):
  - Nombre del contacto dominado por un script NO permitido (chino/cirílico/… en un
    grupo latino) -> reclamo en otro alfabeto.
  - Nombre o vCard con URL / enlace t.me·wa.me / @handle -> un contacto legítimo no
    lleva enlaces promocionales en el nombre.
Falsos positivos > negativos: un contacto con nombre latino normal NO dispara. El
score es alto pero < 100 para que el trust score pueda degradarlo (un veterano que
comparta el contacto de un amigo extranjero pasa por revisión, no ban directo).
"""
from __future__ import annotations

import re

from telegram import Message

from . import Hit
from .unicode_script import non_allowed_ratio

# URL, enlaces de mensajería o @handle "largo" (evita @ suelto o menciones cortas).
_LINK_RE = re.compile(r"(https?://|\bt\.me/|\bwa\.me/|\bwhatsapp\b|@[A-Za-z0-9_]{4,})", re.I)


def check(
    msg: Message,
    allowed_scripts,
    non_latin_threshold: float,
    is_first_msg: bool = True,
) -> Hit:
    contact = getattr(msg, "contact", None)
    if contact is None:
        return Hit.none()
    first = getattr(contact, "first_name", None) or ""
    last = getattr(contact, "last_name", None) or ""
    name = f"{first} {last}".strip()
    vcard = getattr(contact, "vcard", None) or ""

    reasons: list[str] = []
    score = 0

    # 1) Nombre en script no permitido (el reclamo va en el propio nombre).
    if name:
        ratio, dominant = non_allowed_ratio(name, allowed_scripts)
        if ratio >= non_latin_threshold:
            score = max(score, 80)
            reasons.append(f"nombre del contacto en «{dominant}» (ratio={ratio:.0%})")

    # 2) Enlace / handle promocional en el nombre o en el vCard.
    if _LINK_RE.search(name) or _LINK_RE.search(vcard):
        score = max(score, 90)
        reasons.append("el contacto incluye enlaces o handles promocionales")

    if score == 0:
        return Hit.none()
    return Hit(
        rule="contact_spam",
        score=score,
        reason="Contacto compartido con reclamo de spam: " + "; ".join(reasons),
        payload={"name": name[:80], "first_msg": is_first_msg},
    )
