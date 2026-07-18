"""Catálogo de frases sarcásticas al banear, por regla disparada.

Tono: humor seco, "hasta lueguito", irónico. Sin insultos. Frase corta y
punzante. En plural cuando es batch.

Diseño: cada regla tiene 8-12 variantes, se elige una al azar. Las frases NO
viven aquí sino en los paquetes de idioma (`src/locales/*.json`), numeradas desde
1: `quip.<regla>.1`, `quip.<regla>.2`... Traducir el bot es escribir chistes que
funcionen en ese idioma, no traducir estos literalmente, así que cada idioma
puede tener MÁS o MENOS frases por categoría (ver `_phrases`).

El mensaje resultante se publica en el grupo y se borra a los `PUBLIC_QUIP_DELETE_AFTER_S`
segundos (default 1h para bans individuales, 0 = nunca para batches).
"""
from __future__ import annotations

import random

from .i18n import DEFAULT, current_lang, t
from .locales import STRINGS

# Reglas CON catálogo de quips. Una regla que no esté aquí no tiene frase (pick
# devuelve None y el ban es silencioso), igual que antes de mover los textos a JSON.
# El catálogo real de cada una son las claves `quip.<regla>.<n>` del idioma.
_RULES: tuple[str, ...] = (
    "non_allowed_script",
    "external_mention_or_link",
    "cas_match",
    "reaction_farming",
    "url_blocklist",
    "manual_admin_ban",
    "manual_admin_unban",
    "federation_known_ban",
    "inline_buttons_from_user",
    "photos_batch_upload",
    "commercial_ad",
    "dormant_bot_mention",
    "bio_spam",
    "obvious_spam_profile",
    "forward_first_msg",
    "first_msg_media",
    "jfm_too_fast",
    "jfm_fast",
    "jfm_cron",
    "tg_deeplink",
    "premium_new_link",
    "lols_match",
    "learned_similarity",
    "warns_limit",
)


def _phrases(prefix: str) -> list[str]:
    """Frases `<prefix>.1`, `.2`... del idioma actual, hasta el primer índice que falte.

    Se leen de STRINGS y NO con `t()` A PROPÓSITO: `t()` cae al español cuando a un
    idioma le falta una clave, así que un idioma con 5 chistes donde el español tiene
    20 devolvería frases en español de la 6 en adelante (catálogo mezclado en pleno
    grupo). Aquí cada idioma aporta EXACTAMENTE las frases que ha escrito.

    Si el idioma no tiene NINGUNA frase de esa categoría se cae entero al idioma de
    referencia: mejor un quip en español que una lista vacía, porque `random.choice([])`
    lanzaría IndexError en mitad de un ban. Si tampoco la tiene, devuelve [] y quien
    llama decide (pick → None → ban silencioso).
    """
    for lang in (current_lang(), DEFAULT):
        pack = STRINGS.get(lang) or {}
        out: list[str] = []
        i = 1
        while (frase := pack.get(f"{prefix}.{i}")) is not None:
            out.append(frase)
            i += 1
        if out:
            return out
    return []


def _format_name(username: str | None, user_id: int | None, first_name: str | None = None) -> str:
    """Formatea identidad SIN crear link clicable al perfil.

    Razón: muchos spammers tienen contenido inapropiado en su perfil
    (porno, scams, etc.). Mostrar @username o un link tg://user?id=
    le daría visibilidad. Mostramos first_name + (id: N) que identifica
    al usuario sin abrir su perfil.
    """
    import html as _h
    nombre = (first_name or "user").strip()
    nombre = _h.escape(nombre[:40]) if nombre else "user"
    if user_id:
        return f"{nombre} (id: <code>{user_id}</code>)"
    return nombre


def _script_name(dom: str) -> str:
    """Nombre coloquial del script Unicode ('han' → chino / Chinese).

    Si el idioma no nombra ese script, se devuelve el código crudo ('thai'), que es
    más útil que una clave suelta en medio de la frase.
    """
    key = f"quip.script.{dom or 'other'}"
    txt = t(key)
    return dom if txt == key else txt


def _format_extra(rule: str, payload: dict | None) -> str:
    p = payload or {}
    if rule == "non_allowed_script":
        sub = p.get("non_allowed_script") or p
        return _script_name(sub.get("dominant_script", ""))
    if rule == "reaction_farming":
        sub = p.get("reaction_farming") or p
        n = sub.get("reactions", "?")
        s = sub.get("window_s", "?")
        return t(f"quip.extra.{rule}", n=n, s=s)
    if rule == "url_blocklist":
        sub = p.get("url_blocklist") or p
        hosts = sub.get("hosts", [])
        return ", ".join(hosts) if hosts else t(f"quip.extra.{rule}")
    if rule == "external_mention_or_link":
        sub = p.get("external_mention_or_link") or p
        n = len(sub.get("external_mentions", [])) + len(sub.get("external_tg_links", []))
        return t(f"quip.extra.{rule}", n=n)
    if rule in ("jfm_too_fast", "jfm_fast", "jfm_cron"):
        sub = p.get(rule) or p
        return str(sub.get("delta_s", "?"))
    return ""


def pick(
    rule: str,
    username: str | None,
    user_id: int | None,
    payload: dict | None,
    first_name: str | None = None,
) -> str | None:
    """Devuelve un quip ya formateado, o None si la regla no tiene catálogo.

    Para reglas compuestas (rule1+rule2), usa la primera reconocida.
    """
    name = _format_name(username, user_id, first_name)
    candidates = []
    for sub_rule in rule.split("+"):
        if sub_rule in _RULES:
            candidates.append(sub_rule)
    if not candidates:
        return None
    chosen_rule = candidates[0]
    frases = _phrases(f"quip.{chosen_rule}")
    if not frases:
        return None
    extra = _format_extra(chosen_rule, payload)
    template = random.choice(frases)
    return template.format(name=name, extra=extra)


def _reason_summary(username: str | None, user_id: int, info: dict) -> str:
    name = _format_name(username, user_id, info.get("first_name"))
    if info.get("cas_offenses", 0) > 0:
        return f"{name} , CAS offenses={info['cas_offenses']}"
    reasons = info.get("reasons") or []
    if reasons:
        return f"{name} , {', '.join(reasons[:3])}"
    if info.get("rule"):
        return f"{name} , {info['rule']}"
    return name


def batch_summary(items: list[dict], category: str = "cas_match") -> str:
    """Construye un mensaje en batch listando todos los baneados.

    Si items contiene un solo elemento, usa el quip individual (en singular).
    """
    if not items:
        return ""
    if len(items) == 1:
        it = items[0]
        rule = it.get("rule") or category
        payload = {"cas_offenses": it.get("cas_offenses", 0)} if rule == "cas_match" else (it.get("payload") or {})
        msg = pick(rule=rule, username=it.get("username"), user_id=it.get("user_id"), payload=payload)
        if msg:
            return msg
        return _reason_summary(it.get("username"), it.get("user_id", 0), it)
    # Categoría sin cabeceras propias (p.ej. una nueva sin traducir): usa las de CAS,
    # que es la limpieza en batch más habitual.
    cabeceras = _phrases(f"quip.batch.{category}") or _phrases("quip.batch.cas_match")
    lines: list[str] = [random.choice(cabeceras), ""] if cabeceras else [""]
    for i, it in enumerate(items, 1):
        line = _reason_summary(it.get("username"), it.get("user_id", 0), it)
        lines.append(f"{i}. {line}")
    lines.append("")
    outros = _phrases("quip.outro")
    if outros:
        lines.append(f"<i>{random.choice(outros)}</i>")
    lines.append(f"<i>{t('quip.batch.total', n=len(items))}</i>")
    return "\n".join(lines)
