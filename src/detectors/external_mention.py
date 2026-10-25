"""Detector de menciones externas y enlaces a otros grupos/canales Telegram.

Reglas:
- @username mencionado en mensaje, pero ese username NO está en el grupo → spam.
- text_mention (entity con user_id) a usuario que no pertenece al chat → spam.
- URL/text_link con host t.me/telegram.me/... apuntando a otro grupo/canal
  → spam. EXCEPCIÓN: si apunta al propio chat (t.me/PROPIO_USERNAME/...) se
  permite como enlace interno (mensajes anclados, posts del mismo grupo).
- Refinamiento 2026-05: si hay mención externa y el texto que la acompaña
  está vacío, es muy corto, o no parece del IDIOMA DEL BOT → score muy alto
  (ban directo). Antes ese "no parece" estaba clavado al español, así que una
  instalación en inglés se comía la puntuación máxima por escribir en inglés.
  De un idioma sin vocabulario propio se asume que sí: no saber no puede acusar.
- Erratas (25-oct-2026): un @usuario que nadie conoce y que está a una tecla del
  de un miembro del chat no es un externo, es un dedo torpe. Ver `posible_errata`.
"""
from __future__ import annotations

from urllib.parse import urlparse

from telegram import Message, MessageEntity

from .. import lang
from ..i18n import t
from . import Hit, trozo_entidad

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


def handles_mencionados(msg: Message) -> list[str]:
    """Los @usuario escritos a mano en el mensaje, sin la arroba."""
    text = _text_of(msg)
    return [trozo_entidad(text, e.offset, e.length).lstrip("@")
            for e in _extract_entities(msg) if e.type == MessageEntity.MENTION]


def _distancia(a: str, b: str, tope: int) -> int:
    """Ediciones para pasar de `a` a `b`, contando como UNA el cruce de dos letras
    vecinas (Moliko/Molkio). Deja de contar al pasar de `tope`."""
    if abs(len(a) - len(b)) > tope:
        return tope + 1
    antes, fila = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        nueva = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            nueva[j] = min(fila[j] + 1, nueva[j - 1] + 1,
                           fila[j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                nueva[j] = min(nueva[j], antes[j - 2] + 1)
        if min(nueva) > tope:
            return tope + 1
        antes, fila = fila, nueva
    return fila[-1]


def _tolerancia(n: int) -> int:
    """Cuántas teclas de error se perdonan según lo largo que es el @usuario."""
    return 2 if n >= 10 else (1 if n >= 5 else 0)


def posible_errata(handle: str, candidatos) -> str | None:
    """El @usuario de un miembro al que `handle` se parece lo bastante, o None.

    Una tecla de más, de menos, cambiada o dos cruzadas (dos si el nombre pasa de
    nueve letras). Caso real (25-oct-2026, Domótica): «Era porque @Moliko tenía
    varios Spot», con el miembro @Molkio, 382 mensajes. Si dos miembros quedan
    igual de cerca no se adivina: una sugerencia equivocada señala a otra persona.
    Medido sobre 786 textos guardados: de 111 menciones a desconocidos (casi todas
    bots de spam con nombres al azar), solo esta se parece a un miembro.
    """
    h = handle.lstrip("@").lower()
    tope = _tolerancia(len(h))
    if not tope:
        return None
    mejor, elegidos = tope + 1, set()
    for cand in candidatos:
        d = _distancia(h, cand.lower(), tope)
        if d == 0 or d > tope or d > mejor:
            continue
        if d < mejor:
            mejor, elegidos = d, set()
        elegidos.add(cand)
    if len({c.lower() for c in elegidos}) != 1:
        return None
    return next(iter(elegidos))


def erratas_de_mencion(msg: Message, resolve_username, candidatos) -> list[tuple[str, str]]:
    """[(lo escrito, el miembro al que se parece)] de las menciones a desconocidos.

    Solo cuenta un @usuario que el bot NO conoce: si resuelve a alguien, aunque
    no esté en el grupo, es otra persona real y no una errata.
    """
    out: list[tuple[str, str]] = []
    for handle in handles_mencionados(msg):
        if resolve_username(handle) is not None:
            continue
        bien = posible_errata(handle, candidatos)
        if bien and all(handle.lower() != m.lower() for m, _ in out):
            out.append((handle, bien))
    return out


def find_external_user_mentions(
    msg: Message,
    chat_id: int,
    is_user_in_chat,  # callable: (chat_id, user_id) -> bool
    resolve_username,  # callable: (username) -> user_id | None
    ignorar: set[str] | None = None,  # @usuario (en minúsculas) que no cuentan
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
            handle = trozo_entidad(text, ent.offset, ent.length)
            if ignorar and handle.lstrip("@").lower() in ignorar:
                continue
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
            url = trozo_entidad(text, ent.offset, ent.length)
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
    erratas: list[tuple[str, str]] | None = None,
) -> Hit:
    """`erratas`: menciones que el llamador ya ha dado por dedo torpe (ver
    `erratas_de_mencion`); no cuentan como externas."""
    payload: dict = {}
    score = 0
    reasons: list[str] = []

    if detect_user_mentions:
        ignorar = {mal.lower() for mal, _ in erratas or ()}
        externals = find_external_user_mentions(
            msg, chat_id, is_user_in_chat, resolve_username, ignorar=ignorar)
        if externals:
            payload["external_mentions"] = externals
            # Lógica de contexto: ¿el mensaje lleva texto adicional en español?
            ctx_text = _text_without_mentions_and_urls(msg)
            if is_first_msg:
                if not ctx_text or len(ctx_text) < 5:
                    score += 130
                    reasons.append(t("reason.mention_no_context", n=len(externals)))
                elif not lang.parece_del_idioma_activo(ctx_text):
                    score += 130
                    reasons.append(t("reason.mention_not_spanish", text=ctx_text[:50]))
                else:
                    score += 60  # mención con texto español = sospechoso pero no ban directo
                    reasons.append(t("reason.mention_with_context", n=len(externals)))
            else:
                score += 40
                reasons.append(t("reason.mention_external", n=len(externals)))

    if detect_tg_links:
        ext_links = find_external_telegram_links(msg, own_chat_username=own_chat_username)
        if ext_links:
            payload["external_tg_links"] = ext_links
            score += 100 if is_first_msg else 50
            reasons.append(t("reason.external_tg_link", n=len(ext_links)))

    if score == 0:
        return Hit.none()
    return Hit(
        rule="external_mention_or_link",
        score=score,
        reason=" | ".join(reasons),
        payload=payload,
    )
