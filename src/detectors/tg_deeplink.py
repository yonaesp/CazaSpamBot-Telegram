"""Detector de tg:// deeplinks de phishing.

Patrones:
- tg://resolve?domain=USERNAME       — fuerza apertura del perfil/canal sin previsualización
- tg://join?invite=HASH              — invitación a chat privado
- tg://msg?... y tg://share?...      — uso atípico, casi siempre spam
"""
from __future__ import annotations

import re

from telegram import Message, MessageEntity

from . import Hit

_TG_DEEPLINK_RE = re.compile(
    r"tg://(?:resolve\?domain=|join\?invite=|msg\?|share\?|user\?id=|addtheme=|addstickers=|setlanguage=)",
    re.IGNORECASE,
)


def _iter_text_and_urls(msg: Message) -> list[str]:
    out = []
    text = msg.text or msg.caption or ""
    if text:
        out.append(text)
    entities = list(msg.entities or []) + list(msg.caption_entities or [])
    for ent in entities:
        if ent.type == MessageEntity.TEXT_LINK and ent.url:
            out.append(ent.url)
    return out


def check(msg: Message, is_first_msg: bool) -> Hit:
    hits = []
    for s in _iter_text_and_urls(msg):
        for m in _TG_DEEPLINK_RE.finditer(s):
            hits.append(m.group(0))
    if not hits:
        return Hit.none()
    score = 90 if is_first_msg else 50
    return Hit(
        rule="tg_deeplink",
        score=score,
        reason=f"tg:// deeplink sospechoso: {', '.join(set(hits))[:120]}",
        payload={"deeplinks": list(set(hits))},
    )
