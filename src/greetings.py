"""Reacciones amistosas a usuarios educados cuando dan los buenos días/noches/etc.

Diseño:
- Tabla `friendly_greeters(user_id, reactions_json)` configurable por el admin.
- handlers.on_message comprueba si el user es greeter Y el mensaje es saludo.
- Si sí, espera N segundos (default 5) y reacciona con un emoji random.
- Errores de set_message_reaction (emoji no permitido) → fallback silencioso.
"""
from __future__ import annotations

import logging
import random
import re

from telegram import Message
from telegram.error import TelegramError
from telegram.ext import ContextTypes

log = logging.getLogger(__name__)

# Reacciones de Telegram permitidas como fallback si la principal falla
FALLBACK_REACTIONS = ["🫡", "🤝", "🤗"]

GREETING_RE = re.compile(
    r"(?ix)"
    r"\b(?:"
    r"buen[ao]s?\s*(?:d[ií]as?|noches?|tardes?)|"
    r"buen\s*d[ií]a|"
    r"feliz\s*(?:d[ií]a|noche|tarde|lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo|"
    r"fin\s*de\s*semana|semana)|"
    r"que\s+tengas?\s+(?:buen|bonito|lindo|excelente)\s*d[ií]a|"
    r"que\s+descan[se]es?|"
    r"hasta\s+ma[ñn]ana|"
    r"saludos?\s+a\s+todos|"
    r"hola\s+(?:a\s+)?(?:todos|grupo|familia|gente)"
    r")",
)


def is_greeting(text: str | None) -> bool:
    """True si el texto contiene un saludo típico (días/tardes/noches/feliz X)."""
    if not text or len(text) > 200:
        return False
    return bool(GREETING_RE.search(text))


async def react_friendly_delayed(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    reactions: list[str],
    delay: int = 5,
) -> None:
    """Programa una reacción amigable al mensaje tras N segundos."""
    jq = context.application.job_queue
    if jq is None:
        return
    jq.run_once(
        _react_job,
        when=delay,
        data={"chat_id": chat_id, "message_id": message_id, "reactions": reactions},
        name=f"friendly_react_{chat_id}_{message_id}",
    )


async def _react_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    reactions = list(data.get("reactions") or [])
    # Mezclar configuradas con fallback (al final)
    tried = set()
    candidates = reactions + [e for e in FALLBACK_REACTIONS if e not in reactions]
    random.shuffle(candidates)
    for emoji in candidates:
        if emoji in tried:
            continue
        tried.add(emoji)
        try:
            await context.bot.set_message_reaction(
                chat_id=data["chat_id"],
                message_id=data["message_id"],
                reaction=[emoji],
            )
            log.debug("friendly react OK chat=%s msg=%s emoji=%s",
                      data["chat_id"], data["message_id"], emoji)
            return
        except TelegramError as exc:
            # REACTION_INVALID o similar → probar siguiente
            log.debug("friendly react fallo con %s: %s, probando siguiente", emoji, exc)
    log.warning(
        "friendly react agotó todas las opciones para chat=%s msg=%s",
        data["chat_id"], data["message_id"],
    )
