"""Detector de menciones externas y enlaces a otros grupos/canales Telegram.

Reglas:
- @username mencionado en mensaje, pero ese username NO está en el grupo → spam.
- text_mention (entity con user_id) a usuario que no pertenece al chat → spam.
- URL/text_link con host t.me/telegram.me/... apuntando a otro grupo/canal
  → spam. EXCEPCIÓN: si apunta al propio chat (t.me/PROPIO_USERNAME/...) se
  permite como enlace interno (mensajes anclados, posts del mismo grupo).
- Refinamiento 2026-05: si hay mención externa y el texto que la acompaña
  está vacío, es muy corto, o no parece español → score muy alto (ban directo).
"""
from __future__ import annotations

from urllib.parse import urlparse

from telegram import Message, MessageEntity

from .. import lang
from . import Hit

_TG_HOSTS = {"t.me", "telegram.me", "telegram.dog"}


def _extract_entities(msg: Message) -> list[MessageEntity]:
    ents: list[MessageEntity] = []
    if msg.entities:
        ents.extend(msg.entities)
    if msg.caption_entities:
        ents.extend(msg.caption_entities)
    return ents


def _text_of(msg: Message) -> str:
    return msg.text or msg.caption or ""


def find_external_user_mentions(
    msg: Message,
    chat_id: int,
    is_user_in_chat,  # callable: (chat_id, user_id) -> bool
    resolve_username,  # callable: (username) -> user_id | None
) -> list[dict]:
    """Devuelve lista de menciones a usuarios que NO están en el grupo."""
    text = _text_of(msg)
    out: list[dict] = []
    for ent in _extract_entities(msg):
        if ent.type == MessageEntity.TEXT_MENTION and ent.user:
            uid = ent.user.id
            if not is_user_in_chat(chat_id, uid):
                out.append({"type": "text_mention", "user_id": uid, "username": ent.user.username})
        elif ent.type == MessageEntity.MENTION:
            handle = text[ent.offset : ent.offset + ent.length]
            uid = resolve_username(handle)
            if uid is None or not is_user_in_chat(chat_id, uid):
                out.append({"type": "mention", "username": handle, "user_id": uid})
    return out


def find_external_telegram_links(msg: Message, own_chat_username: str | None = None) -> list[str]:
    """Devuelve URLs t.me/... a chats/canales/posts EXTERNOS.

    Excluye t.me/{own_chat_username}/* (enlaces al propio chat: post anclado,
    mensajes específicos del mismo grupo) si se proporciona own_chat_username.
    """
    text = _text_of(msg)
    urls: list[str] = []
    own = (own_chat_username or "").lstrip("@").lower() or None
    for ent in _extract_entities(msg):
        url: str | None = None
        if ent.type == MessageEntity.TEXT_LINK:
            url = ent.url
        elif ent.type == MessageEntity.URL:
            url = text[ent.offset : ent.offset + ent.length]
        if not url:
            continue
        if "://" not in url:
            url = "https://" + url
        try:
            parsed = urlparse(url)
        except ValueError:
            continue
        host = (parsed.netloc or "").lower().lstrip("www.")
        path = parsed.path.strip("/")
        if host not in _TG_HOSTS or not path:
            continue
        # Permitir t.me/joinchat/HASH y t.me/+HASH siempre como externo (es invite link)
        first_seg = path.split("/")[0].lower()
        if own and first_seg == own:
            continue  # enlace interno al propio chat
        urls.append(url)
    return urls


def _text_without_mentions_and_urls(msg: Message) -> str:
    """Devuelve el texto del mensaje sin las menciones/URLs (para evaluar si lleva contexto real)."""
    text = _text_of(msg)
    if not text:
        return ""
    # Quitamos entities mencionando y URLs por posición (de atrás adelante para no romper offsets)
    entities = sorted(_extract_entities(msg), key=lambda e: e.offset, reverse=True)
    for ent in entities:
        if ent.type in (
            MessageEntity.MENTION, MessageEntity.TEXT_MENTION,
            MessageEntity.URL, MessageEntity.TEXT_LINK,
        ):
            text = text[: ent.offset] + text[ent.offset + ent.length :]
    return text.strip()


def check(
    msg: Message,
    chat_id: int,
    is_first_msg: bool,
    detect_user_mentions: bool,
    detect_tg_links: bool,
    is_user_in_chat,
    resolve_username,
    own_chat_username: str | None = None,
) -> Hit:
    payload: dict = {}
    score = 0
    reasons: list[str] = []

    if detect_user_mentions:
        externals = find_external_user_mentions(msg, chat_id, is_user_in_chat, resolve_username)
        if externals:
            payload["external_mentions"] = externals
            # Lógica de contexto: ¿el mensaje lleva texto adicional en español?
            ctx_text = _text_without_mentions_and_urls(msg)
            if is_first_msg:
                if not ctx_text or len(ctx_text) < 5:
                    score += 130
                    reasons.append(f"Mención sin contexto ({len(externals)} externo/s)")
                elif not lang.likely_spanish(ctx_text):
                    score += 130
                    reasons.append(f"Mención + texto NO español: '{ctx_text[:50]}'")
                else:
                    score += 60  # mención con texto español = sospechoso pero no ban directo
                    reasons.append(f"Mención a {len(externals)} externo/s (con contexto ES)")
            else:
                score += 40
                reasons.append(f"Mención a {len(externals)} externo/s")

    if detect_tg_links:
        ext_links = find_external_telegram_links(msg, own_chat_username=own_chat_username)
        if ext_links:
            payload["external_tg_links"] = ext_links
            score += 100 if is_first_msg else 50
            reasons.append(f"Enlace t.me/... a chat externo ({len(ext_links)})")

    if score == 0:
        return Hit.none()
    return Hit(
        rule="external_mention_or_link",
        score=score,
        reason=" | ".join(reasons),
        payload=payload,
    )
