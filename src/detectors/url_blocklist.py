"""Detector de URLs en blocklist (acortadores típicos de spam)."""
from __future__ import annotations

from urllib.parse import urlparse

from telegram import Message, MessageEntity

from . import Hit


def _iter_urls(msg: Message) -> list[str]:
    text = msg.text or msg.caption or ""
    urls: list[str] = []
    entities = list(msg.entities or []) + list(msg.caption_entities or [])
    for ent in entities:
        if ent.type == MessageEntity.TEXT_LINK and ent.url:
            urls.append(ent.url)
        elif ent.type == MessageEntity.URL:
            urls.append(text[ent.offset : ent.offset + ent.length])
    return urls


def check(msg: Message, blocklist: list[str], is_first_msg: bool) -> Hit:
    bad: list[str] = []
    for raw in _iter_urls(msg):
        url = raw if "://" in raw else "https://" + raw
        try:
            host = (urlparse(url).netloc or "").lower().lstrip("www.")
        except ValueError:
            continue
        if any(host == d or host.endswith("." + d) for d in blocklist):
            bad.append(host)
    if not bad:
        return Hit.none()
    score = 60 if is_first_msg else 25
    return Hit(
        rule="url_blocklist",
        score=score,
        reason=f"URL en blocklist: {', '.join(bad)}",
        payload={"hosts": bad},
    )
