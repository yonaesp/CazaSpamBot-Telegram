"""Detector: el canal personal del perfil usado como escaparate de spam.

Telegram permite enlazar un CANAL en el perfil. Es un escaparate aparte de la
bio: una cuenta con la bio vacía, sin foto y sin @username puede llevar ahí un
canal entero de spam, y hasta ahora no lo mirábamos.

Caso real (2026-07-19, grupo de domótica en español): cuenta «Matthew», nombre
latino, sin foto, sin @username y con la bio VACÍA. Pasó todos los filtros de
perfil precisamente por estar vacía. En el perfil llevaba enlazado un canal
titulado «恒泰集团招洗钱车队结账通知频道» cuyo último post reclutaba mulas de
blanqueo.

TENER un canal personal es COMPLETAMENTE LEGÍTIMO: mucha gente enlaza su blog,
su canal de fotos o su proyecto. Lo que se mira aquí NO es el hecho de tener
canal, sino la DISCORDANCIA y el contenido:

  - el título está en un alfabeto que ESE chat no admite (se reutiliza
    `allowed_scripts` y la lógica de `unicode_script`),
  - el nombre del usuario sí está en un alfabeto permitido: disfraz deliberado
    de «vecino de aquí» con el escaparate en otro idioma,
  - el título trae vocabulario de spam (lista editable
    `config/blacklist/personal_channel_keywords.txt`),
  - el perfil no tiene nada más que mirar (sin foto y sin bio), así que el canal
    es su ÚNICO contenido público.

Ninguna señal suelta llega a MIN_SCORE: hacen falta al menos dos. Sin Telethon
no hay título de canal que analizar y el detector simplemente no aplica.
"""
from __future__ import annotations

from collections.abc import Iterable

from ..i18n import t
from ..wordlists import load_and_compile
from . import Hit
from .unicode_script import non_allowed_ratio, script_distribution

# Proporción de letras en alfabeto no permitido a partir de la cual se considera
# que el título «está en otro idioma». Alto a propósito: un título en español con
# una palabra suelta en otro alfabeto no prueba nada.
TITLE_FOREIGN_RATIO = 0.5

# Pesos. Elegidos para que NINGUNO alcance MIN_SCORE por sí solo.
SCORE_FOREIGN_TITLE = 40   # el escaparate está en un alfabeto ajeno al chat
SCORE_NAME_MISMATCH = 45   # ...y el nombre NO. Es la señal más fuerte del caso real
SCORE_KEYWORDS = 75        # el título dice a qué se dedica
SCORE_HIDDEN_PROFILE = 25  # sin foto ni bio: el canal es su único contenido

# Umbral de emisión. Coincide con BAN_SCORE por defecto porque el enganche del
# join banea directo: si no hay evidencia para banear, mejor no devolver nada y
# dejar que el flujo normal de verificación decida (falsos positivos > falsos
# negativos).
MIN_SCORE = 100

# Vocabulario ilícito en el título del canal. Editable en
# `config/blacklist/personal_channel_keywords.txt` (defaults de respaldo aquí).
#
# Se compila SIN `\b(?:...)\b`: el chino y el japonés no separan palabras con
# espacios, así que el envoltorio dejaría muertos todos los patrones CJK. A
# cambio, los patrones latinos traen sus propios `\b`.
_DEFAULT_CHANNEL_KEYWORDS = [
    # CJK: blanqueo, mulas, juego, tarjetas robadas
    r"洗钱", r"跑分", r"承兑", r"博彩", r"赌场", r"娱乐城", r"卡商", r"四件套",
    # Cirílico: cobro en negro, apuestas, documentos falsos
    r"обнал", r"ставк[аи]", r"казино", r"документы\s*под\s*ключ",
    # Latino: expresiones compuestas, nunca palabras sueltas comunes
    r"\bmoney\s+laundering\b", r"\bpump\s+and\s+dump\b",
    r"\b(?:crypto|forex|binary)\s+signals?\b", r"\bcasino\s+bonus\b",
    r"\bfake\s+(?:documents?|passports?|ids?)\b", r"\bhacked\s+accounts?\b",
    r"\bcash\s?out\s+(?:team|crew|service)\b", r"\bescort\s+service\b",
    r"\bonlyfans\b", r"\bblanqueo\s+de\s+(?:capitales|dinero)\b",
]


def _keywords_re():
    return load_and_compile(
        "personal_channel_keywords.txt", _DEFAULT_CHANNEL_KEYWORDS, boundaries=False,
    )


def _name_fully_allowed(
    first_name: str | None, last_name: str | None, username: str | None,
    allowed: set[str],
) -> bool:
    """True si el nombre visible tiene letras y TODAS son de alfabetos permitidos.

    Un nombre sin letras (solo emojis o números) devuelve False: no prueba que el
    usuario se esté disfrazando de local, y cobrarle el plus de discordancia por
    llamarse «⭐⭐⭐» sería inventarse evidencia.
    """
    name = " ".join(p for p in (first_name, last_name, username) if p).strip()
    counts = script_distribution(name)
    if not counts:
        return False
    return all(script in allowed for script in counts)


def check(
    channel_title: str | None,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
    allowed_scripts: Iterable[str] = ("latin",),
    has_photo: bool = True,
    has_bio: bool = True,
    ratio_threshold: float = TITLE_FOREIGN_RATIO,
) -> Hit:
    """Analiza el título del canal personal. Sin canal (o sin Telethon) no dispara."""
    title = (channel_title or "").strip()
    if not title:
        return Hit.none()

    allowed = {s.lower() for s in allowed_scripts}
    score = 0
    reasons: list[str] = []
    payload: dict = {"channel_title": title[:200]}

    ratio, dominant = non_allowed_ratio(title, allowed)
    if ratio >= ratio_threshold:
        score += SCORE_FOREIGN_TITLE
        reasons.append(
            t("reason.personal_channel_foreign", script=dominant, ratio=f"{ratio:.0%}"))
        payload["dominant_script"] = dominant
        payload["ratio"] = ratio
        # El plus de discordancia solo tiene sentido si el título ya es ajeno.
        if _name_fully_allowed(first_name, last_name, username, allowed):
            score += SCORE_NAME_MISMATCH
            reasons.append(t("reason.personal_channel_mismatch"))
            payload["name_mismatch"] = True

    if _keywords_re().search(title):
        score += SCORE_KEYWORDS
        reasons.append(t("reason.personal_channel_keywords"))
        payload["keywords"] = True

    if not has_photo and not has_bio:
        score += SCORE_HIDDEN_PROFILE
        reasons.append(t("reason.personal_channel_hidden"))
        payload["hidden_profile"] = True

    if score < MIN_SCORE:
        return Hit.none()

    payload["score"] = score
    return Hit(
        rule="personal_channel_spam",
        score=min(score, 200),
        reason=t("reason.personal_channel_spam", details=" + ".join(reasons)),
        payload=payload,
    )
