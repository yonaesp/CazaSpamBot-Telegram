"""/scan — diagnóstico: responde a un mensaje (reenviado o no) y el bot te dice
qué reglas de CONTENIDO dispararía si lo enviara alguien nuevo, y qué estructura
tiene (texto, contacto, botones inline, media, origen del forward). Solo admin.

No modera nada: es una herramienta para el admin, útil cuando llega un formato
raro y quieres saber si el bot lo pillaría. Corre los detectores que dependen solo
del mensaje (asume primer mensaje = evaluación más estricta); no los que necesitan
historial/Telethon (trust, cas/lols, jfm, etc.).
"""
from __future__ import annotations

import html as _h

from telegram import Update
from telegram.ext import ContextTypes

from .config import Config
from .detectors import commercial_ad as comad_det
from .detectors import contact_spam as contact_det
from .detectors import emoji_only as emoji_det
from .detectors import forward_first_msg as fwd_det
from .detectors import inline_buttons as buttons_det
from .detectors import tg_deeplink as tgdeep_det
from .detectors import unicode_script as script_det
from .detectors import url_blocklist as url_det


def _structure(msg) -> list[str]:
    """Describe qué ES el mensaje (para entender 'formatos raros')."""
    out: list[str] = []
    contact = getattr(msg, "contact", None)
    if contact is not None:
        name = f"{getattr(contact, 'first_name', '') or ''} {getattr(contact, 'last_name', '') or ''}".strip()
        phone = getattr(contact, "phone_number", None) or "?"
        out.append(f"📇 <b>Contacto compartido</b> · nombre: <code>{_h.escape(name)}</code> · tel: <code>{_h.escape(phone)}</code>")
    rm = getattr(msg, "reply_markup", None)
    kb = getattr(rm, "inline_keyboard", None) if rm else None
    if kb:
        n = sum(len(r) for r in kb)
        urls = [b.url for r in kb for b in r if getattr(b, "url", None)]
        out.append(f"🔘 <b>{n} botón(es) inline</b>" + (f" → {len(urls)} URL" if urls else " (callback)"))
    origin = getattr(msg, "forward_origin", None)
    fwd_chat = getattr(msg, "forward_from_chat", None)
    if origin is not None or fwd_chat is not None:
        src = ""
        if fwd_chat is not None:
            src = f" desde {getattr(fwd_chat, 'type', '?')} «{_h.escape(getattr(fwd_chat, 'title', '') or '')}»"
        out.append(f"↪️ <b>Reenviado</b>{src}")
    has_media = any(getattr(msg, a, None) for a in
                    ("photo", "video", "animation", "sticker", "document", "video_note", "voice", "audio"))
    if has_media:
        out.append("🖼️ Lleva media (foto/vídeo/sticker/…)")
    txt = getattr(msg, "text", None) or getattr(msg, "caption", None)
    if txt:
        prev = txt[:120].replace("\n", " ")
        out.append(f"📝 Texto: <code>{_h.escape(prev)}</code>")
    if not out:
        out.append("(mensaje sin texto, contacto, botones ni media reconocibles)")
    return out


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.bot_data["cfg"]
    user = update.effective_user
    if not user or user.id != cfg.admin_user_id:
        return
    msg = update.effective_message
    target = msg.reply_to_message if msg else None
    if target is None:
        await msg.reply_text(
            "🔎 <b>/scan</b> — reenvíame (o trae al DM) el mensaje sospechoso, "
            "respóndele con <code>/scan</code> y te digo si el bot lo detectaría y por qué.",
            parse_mode="HTML",
        )
        return

    hits = [
        script_det.check(target.text or target.caption, is_first_msgs=True,
                         allowed_scripts=cfg.allowed_scripts,
                         threshold=cfg.non_latin_ratio_threshold),
        buttons_det.check(target),
        contact_det.check(target, cfg.allowed_scripts, cfg.non_latin_ratio_threshold),
        url_det.check(target, cfg.url_blocklist, is_first_msg=True),
        tgdeep_det.check(target, is_first_msg=True),
        comad_det.check(target, is_first_msg=True),
        emoji_det.check(target, is_first_msg=True),
        fwd_det.check(target, is_first_msg=True, seconds_since_first_seen=0.0),
    ]
    real = [h for h in hits if h]

    lines = ["🔎 <b>Resultado del scan</b>", ""]
    lines += _structure(target)
    lines.append("")
    if real:
        total = sum(h.score for h in real)
        lines.append(f"✅ <b>SÍ se detectaría</b> — {len(real)} regla(s), score total {total}:")
        for h in sorted(real, key=lambda x: -x.score):
            lines.append(f"  • <code>{h.rule}</code> (score {h.score}) — {_h.escape(h.reason)}")
        lines.append("")
        lines.append("<i>La acción real (ban/kick/aviso) depende además del trust del usuario.</i>")
    else:
        lines.append("❌ <b>NO dispararía ninguna regla de contenido.</b>")
        lines.append("<i>Ojo: no cubre reglas por perfil/listas (CAS, lols, obvious_profile) "
                     "que dependen de quién lo envía.</i>")

    await msg.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
