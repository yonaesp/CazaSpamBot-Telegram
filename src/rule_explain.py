"""Traduce los identificadores técnicos de regla (p.ej. `inline_buttons_from_user`)
a una explicación breve y comprensible para los avisos al admin."""
from __future__ import annotations

RULE_EXPLANATIONS: dict[str, str] = {
    # --- Perfil / cuenta ---
    "obvious_spam_profile": "Perfil con nombre o usuario en caracteres no latinos (patrón típico de cuenta spam).",
    "bio_spam": "Su bio/descripción tenía spam (enlace de invitación + palabras o emojis sospechosos).",
    "photos_batch_upload": "Subió varias fotos de perfil en segundos (identidad robada, típico de bots).",
    "premium_new_link": "Cuenta Premium recién creada que compartía un enlace.",
    "dormant_bot_mention": "Cuenta dormida más de un año que reapareció mencionando a un bot (probable cuenta hackeada).",
    # --- Contenido del mensaje ---
    "commercial_ad": "Anuncio comercial o promoción (ofertas de dinero/empleo, enlaces, etc.).",
    "inline_buttons_from_user": "Su mensaje llevaba botones (inline keyboard): algo que en la práctica solo hacen los bots.",
    "external_mention_or_link": "Menciones a usuarios externos o enlaces a otros grupos en su primer mensaje.",
    "url_blocklist": "Compartió un enlace acortador de la lista negra (bit.ly, tinyurl, etc.).",
    "tg_deeplink": "Enlace tg:// de redirección o phishing.",
    "non_allowed_script": "Escribió en un alfabeto no permitido (por ejemplo chino o cirílico) en su primer mensaje: patrón clásico de spam.",
    "contact_spam": "Compartió una tarjeta de contacto cuyo nombre era el propio anuncio (alfabeto extranjero o con enlaces): truco para colar spam esquivando los filtros de texto.",
    "emoji_only_first_msg": "Su primer mensaje eran solo emojis (captación de atención típica de spam).",
    "forward_first_msg": "Su primer mensaje fue un reenvío de un canal o bot (patrón de spam).",
    "first_msg_media": "Su primer mensaje fue una foto o vídeo, con un perfil sospechoso.",
    "via_bot_spam": "Mensaje enviado a través de otro bot con contenido de spam.",
    "learned_similarity": "El mensaje se parecía mucho a spam que ya le marcaste antes al bot.",
    # --- Comportamiento ---
    "jfm_fast": "Escribió muy rápido tras entrar (comportamiento automatizado).",
    "jfm_too_fast": "Escribió casi al instante de entrar (demasiado rápido para un humano: es un bot).",
    "jfm_cron": "Entró y escribió con un patrón temporal exacto (bot programado).",
    "reaction_farming": "Puso muchas reacciones en pocos segundos sin escribir (farmeo de reacciones).",
    "antiflood": "Envió demasiados mensajes seguidos en pocos segundos (flood).",
    "flood_confirmed_bot": "Flood confirmado como bot.",
    # --- Listas negras externas ---
    "cas_match": "Aparece en la lista negra colaborativa CAS (spammer confirmado en varios grupos).",
    "cas_low_offense": "Aparece en la lista CAS con pocas denuncias (se envió a revisión).",
    "cas_match_trusted_review": "Aparece en CAS pero tiene historial en el grupo (se envió a revisión).",
    "lols_match": "Aparece en la lista negra lols.bot (spammer conocido).",
    "lols_match_trusted_review": "Aparece en lols.bot pero tiene historial (se envió a revisión).",
    # --- Federación / verificación / moderación ---
    "federation_known_ban": "Ya estaba baneado en otro de tus grupos (ban sincronizado por federación).",
    "verification_suspicious_timeout": "Cuenta sospechosa que no verificó a tiempo (no pulsó «Soy humano»).",
    "verification_reminder_timeout": "No verificó que era humano ni siquiera tras el recordatorio.",
    "warns_limit": "Alcanzó el límite de avisos (warns).",
    "manual_admin_ban": "Ban manual hecho por el admin.",
    "manual_review_ban": "Baneado por el admin al revisar un perfil sospechoso (modo revisión).",
}


def explain(rule: str) -> str:
    """Explicación comprensible de una regla (o combinación `a+b`). '' si no se conoce."""
    if not rule:
        return ""
    seen: list[str] = []
    for part in rule.split("+"):
        exp = RULE_EXPLANATIONS.get(part.strip())
        if exp and exp not in seen:
            seen.append(exp)
    if not seen:
        return ""
    if len(seen) == 1:
        return seen[0]
    return " · ".join(seen)
