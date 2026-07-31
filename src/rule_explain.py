"""Traduce los identificadores técnicos de regla (p.ej. `inline_buttons_from_user`)
a una explicación breve y comprensible para los avisos al admin.

El TEXTO vive en los paquetes de idioma (`src/locales/*.json`) bajo la clave
`rule.<id_de_regla>`. Aquí solo queda el inventario de reglas que tienen explicación.
"""
from __future__ import annotations

from .i18n import t

# Inventario canónico de reglas con explicación. Se mantiene aquí (y no derivado de
# los JSON) a propósito: es la lista que audita el meta-test de tests/, y así añadir
# un detector obliga a pasar por este archivo aunque el texto esté en otro sitio.
KNOWN_RULES: frozenset[str] = frozenset({
    # --- Perfil / cuenta ---
    "obvious_spam_profile",
    "bio_spam",
    "photos_batch_upload",
    "personal_channel_spam",
    "premium_new_link",
    "story_share",
    "dormant_bot_mention",
    # --- Contenido del mensaje ---
    "commercial_ad",
    "investment_scam",
    "inline_buttons_from_user",
    "external_mention_or_link",
    "url_blocklist",
    "tg_deeplink",
    "non_allowed_script",
    "contact_spam",
    "external_quote_channel",
    "emoji_only_first_msg",
    "forward_first_msg",
    "first_msg_media",
    "via_bot_spam",
    "learned_similarity",
    # --- Comportamiento ---
    "jfm_fast",
    "jfm_too_fast",
    "jfm_cron",
    "reaction_farming",
    "antiflood",
    "flood_confirmed_bot",
    # --- Listas negras externas ---
    "cas_match",
    "cas_low_offense",
    "cas_match_trusted_review",
    "lols_match",
    "lols_match_trusted_review",
    # --- Federación / verificación / moderación ---
    "federation_known_ban",
    "verification_suspicious_timeout",
    "verification_reminder_timeout",
    "warns_limit",
    "manual_admin_ban",
    "manual_review_ban",
})


def _text(rule: str) -> str:
    """Explicación traducida de UNA regla; '' si no hay ninguna disponible.

    Doble guarda deliberada, porque quien llama encadena
    `explain(...) or decision.reason or <genérico>` y necesita un valor FALSY:

    1. La regla debe estar en `KNOWN_RULES` (inventario de este módulo).
    2. `t()` devuelve LA PROPIA CLAVE cuando falta en los paquetes de idioma, y
       «rule.loquesea» es una cadena no vacía → truthy → el admin vería el
       identificador crudo en pantalla en vez del motivo de respaldo. Por eso se
       compara el resultado con la clave pedida y se descarta si coinciden.
    """
    if rule not in KNOWN_RULES:
        return ""
    key = f"rule.{rule}"
    txt = t(key)
    return "" if txt == key else txt


def explain(rule: str) -> str:
    """Explicación comprensible de una regla (o combinación `a+b`). '' si no se conoce."""
    if not rule:
        return ""
    seen: list[str] = []
    for part in rule.split("+"):
        exp = _text(part.strip())
        if exp and exp not in seen:
            seen.append(exp)
    if not seen:
        return ""
    if len(seen) == 1:
        return seen[0]
    return " · ".join(seen)
