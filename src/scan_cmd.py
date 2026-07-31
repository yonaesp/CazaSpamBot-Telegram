"""/scan — diagnóstico: responde a un mensaje (reenviado o no) y el bot te dice
qué reglas de CONTENIDO dispararía si lo enviara alguien nuevo, y qué estructura
tiene (texto, contacto, botones inline, media, enlaces ocultos en entidades, cita
a otro chat, blockquote, forward). Solo admin.

No modera nada: es una herramienta para el admin, útil cuando llega un formato
raro y quieres saber si el bot lo pillaría. Corre los detectores que dependen solo
del mensaje (asume primer mensaje = evaluación más estricta); no los que necesitan
historial/Telethon (trust, cas/lols, jfm, etc.).

Aviso: al REENVIAR un mensaje al DM, Telegram conserva el texto y sus entidades
(text_link, blockquote) pero suele PERDER el contexto de respuesta/cita a otro chat
(external_reply). Para diagnosticar ese vector, /scan es más fiable ejecutado sobre
el mensaje original en el grupo (respondiéndole con /scan) que sobre el reenvío.
"""
from __future__ import annotations

import html as _h
import time

from telegram import Update
from telegram.ext import ContextTypes

from .config import Config
from .db import DB
from .detectors import commercial_ad as comad_det
from .detectors import contact_spam as contact_det
from .detectors import emoji_only as emoji_det
from .detectors import external_mention as ext_det
from .detectors import external_reply as extreply_det
from .detectors import forward_first_msg as fwd_det
from .detectors import inline_buttons as buttons_det
from .detectors import tg_deeplink as tgdeep_det
from .detectors import unicode_script as script_det
from .detectors import url_blocklist as url_det
from .i18n import t


def _entity_urls(msg) -> list[str]:
    """URLs escondidas en entidades (text_link) o URLs en texto plano."""
    urls: list[str] = []
    text = msg.text or msg.caption or ""
    for ent in (list(msg.entities or []) + list(msg.caption_entities or [])):
        if ent.type == "text_link" and getattr(ent, "url", None):
            urls.append(ent.url)
        elif ent.type == "url":
            urls.append(text[ent.offset:ent.offset + ent.length])
    return urls


def _has_blockquote(msg) -> bool:
    for ent in (list(msg.entities or []) + list(msg.caption_entities or [])):
        if ent.type in ("blockquote", "expandable_blockquote"):
            return True
    return False


def _structure(msg) -> list[str]:
    """Describe qué ES el mensaje (para entender 'formatos raros')."""
    out: list[str] = []
    contact = getattr(msg, "contact", None)
    if contact is not None:
        name = f"{getattr(contact, 'first_name', '') or ''} {getattr(contact, 'last_name', '') or ''}".strip()
        phone = getattr(contact, "phone_number", None) or "?"
        out.append(t("scan.contact", name=_h.escape(name), phone=_h.escape(phone)))
    rm = getattr(msg, "reply_markup", None)
    kb = getattr(rm, "inline_keyboard", None) if rm else None
    if kb:
        n = sum(len(r) for r in kb)
        urls = [b.url for r in kb for b in r if getattr(b, "url", None)]
        extra = t("scan.buttons_urls", n=len(urls)) if urls else t("scan.buttons_callback")
        out.append(t("scan.buttons", n=n, extra=extra))
    # Cita a un mensaje de OTRO chat (external_reply): el "quote etiquetado" que al
    # pulsar lleva a un canal externo. Vector nuevo de spam.
    er = getattr(msg, "external_reply", None)
    if er is not None:
        erchat = getattr(er, "chat", None)
        dest = ""
        if erchat is not None:
            uname = getattr(erchat, "username", None)
            dest = t("scan.er_dest", ctype=getattr(erchat, "type", "?"),
                     title=_h.escape(getattr(erchat, "title", "") or ""))
            if uname:
                dest += t("scan.er_username", username=_h.escape(uname))
        out.append(t("scan.external_reply", dest=dest))
    q = getattr(msg, "quote", None)
    if q is not None and getattr(q, "text", None):
        out.append(t("scan.quote", text=_h.escape(q.text[:80])))
    if _has_blockquote(msg):
        out.append(t("scan.blockquote"))
    via = getattr(msg, "via_bot", None)
    if via is not None:
        out.append(t("scan.via_bot", username=_h.escape(getattr(via, "username", "") or "?")))
    ent_urls = _entity_urls(msg)
    if ent_urls:
        shown = ", ".join(_h.escape(u) for u in ent_urls[:5])
        out.append(t("scan.links", links=shown))
    origin = getattr(msg, "forward_origin", None)
    fwd_chat = getattr(msg, "forward_from_chat", None)
    if origin is not None or fwd_chat is not None:
        src = ""
        if fwd_chat is not None:
            src = t("scan.fwd_src", ctype=getattr(fwd_chat, "type", "?"),
                    title=_h.escape(getattr(fwd_chat, "title", "") or ""))
        out.append(t("scan.forwarded", src=src))
    has_media = any(getattr(msg, a, None) for a in
                    ("photo", "video", "animation", "sticker", "document", "video_note", "voice", "audio"))
    if has_media:
        out.append(t("scan.media"))
    txt = getattr(msg, "text", None) or getattr(msg, "caption", None)
    if txt:
        prev = txt[:160].replace("\n", " ")
        out.append(t("scan.text", text=_h.escape(prev)))
    if not out:
        out.append(t("scan.nothing"))
    return out


# Cuánto espera el bot el mensaje tras un `/scan` a secas. Corto a propósito: si el
# admin se olvida, lo siguiente que escriba en el DM debe recibir la ayuda normal, no
# acabar escaneado por sorpresa media hora después.
_ESPERA_TTL_S = 300


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    user = update.effective_user
    if not user or user.id != cfg.admin_user_id:
        return
    msg = update.effective_message
    target = msg.reply_to_message if msg else None
    if target is None:
        # En el DM el mensaje no tiene por qué existir todavía: el bot se queda
        # esperando el reenvío, que es el orden natural (primero el comando, luego
        # el mensaje). En grupo NO se hace: capturar el siguiente mensaje de
        # cualquiera sería impredecible para el resto de la gente.
        if update.effective_chat is not None and update.effective_chat.type == "private":
            context.user_data["scan_await"] = time.time()
            await msg.reply_text(t("scan.await"), parse_mode="HTML")
        else:
            await msg.reply_text(t("scan.usage"), parse_mode="HTML")
        return
    await _responder_scan(msg, target, cfg, db)


async def handle_capture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Si un `/scan` está esperando mensaje, escanea este y devuelve True.

    Mismo contrato que `config_panel.handle_capture`: quien llama ya comprobó que
    es el admin en su DM, y si devolvemos True debe hacer return.
    """
    pedido = context.user_data.get("scan_await")
    if not pedido:
        return False
    context.user_data.pop("scan_await", None)   # de un solo uso, aunque falle luego
    if time.time() - pedido > _ESPERA_TTL_S:
        return False                            # caducó: que reciba la ayuda normal
    msg = update.effective_message
    if msg is None:
        return False
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    await _responder_scan(msg, msg, cfg, db)
    return True


async def _responder_scan(msg, target, cfg: Config, db: DB) -> None:
    """Corre los detectores sobre `target` y contesta el informe a `msg`."""
    hits = [
        script_det.check(target.text or target.caption, is_first_msgs=True,
                         allowed_scripts=cfg.allowed_scripts,
                         threshold=cfg.non_latin_ratio_threshold),
        buttons_det.check(target),
        contact_det.check(target, cfg.allowed_scripts, cfg.non_latin_ratio_threshold),
        url_det.check(target, cfg.url_blocklist, is_first_msg=True),
        tgdeep_det.check(target, is_first_msg=True),
        ext_det.check(
            target, chat_id=(target.chat_id if target.chat else 0), is_first_msg=True,
            detect_user_mentions=cfg.detect_external_mentions,
            detect_tg_links=cfg.detect_external_tg_links,
            is_user_in_chat=db.known_user_in_chat,
            resolve_username=db.resolve_username,
            own_chat_username=None,
        ),
        extreply_det.check(target, is_first_msg=True, is_moderated_chat=cfg.is_moderated),
        comad_det.check(target, is_first_msg=True),
        emoji_det.check(target, is_first_msg=True),
        fwd_det.check(target, is_first_msg=True, seconds_since_first_seen=0.0),
    ]
    real = [h for h in hits if h]

    lines = [t("scan.header"), ""]
    lines += _structure(target)
    lines.append("")
    if real:
        total = sum(h.score for h in real)
        lines.append(t("scan.detected", n=len(real), total=total))
        for h in sorted(real, key=lambda x: -x.score):
            lines.append(t("scan.hit", rule=h.rule, score=h.score, reason=_h.escape(h.reason)))
        lines.append("")
        lines.append(t("scan.trust_note"))
    else:
        lines.append(t("scan.not_detected"))
        lines.append(t("scan.profile_note"))

    await msg.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
