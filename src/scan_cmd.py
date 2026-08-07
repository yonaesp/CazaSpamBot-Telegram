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
from .detectors import trozo_entidad
from .detectors import commercial_ad as comad_det
from .detectors import investment_scam as invscam_det
from .detectors import contact_spam as contact_det
from .detectors import emoji_only as emoji_det
from .detectors import external_mention as ext_det
from .detectors import external_reply as extreply_det
from .detectors import forward_first_msg as fwd_det
from .detectors import inline_buttons as buttons_det
from .detectors import offplatform_contact as offplat_det
from .detectors import tg_deeplink as tgdeep_det
from .detectors import unicode_script as script_det
from .detectors import url_blocklist as url_det
from .i18n import t
from . import desofuscar
from . import story_reader


def _entity_urls(msg) -> list[str]:
    """URLs escondidas en entidades (text_link) o URLs en texto plano."""
    urls: list[str] = []
    text = msg.text or msg.caption or ""
    for ent in (list(msg.entities or []) + list(msg.caption_entities or [])):
        if ent.type == "text_link" and getattr(ent, "url", None):
            urls.append(ent.url)
        elif ent.type == "url":
            urls.append(trozo_entidad(text, ent.offset, ent.length))
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
    # Historia (story). Telegram entrega a los bots SOLO `chat` e `id`: ni el texto ni
    # la imagen. Hay que decirlo, porque por fuera parece un mensaje normal y lleno.
    if getattr(msg, "story", None) is not None:
        out.append(t("scan.story"))
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
    # ¿Es un mensaje de BIENVENIDA? Entonces lo que el admin quiere saber no es qué
    # dice el saludo (lo escribió el propio bot, no dice nada), sino quién es el
    # recién llegado. Se redirige al informe de usuario.
    dueno = db.usuario_de_bienvenida(msg.chat_id, target.message_id)
    if dueno is not None:
        from . import scanuser_cmd
        informe = await scanuser_cmd._componer(context, cfg, db, msg.chat_id, dueno)
        await _entregar(context, msg, t("scan.was_welcome") + "\n\n" + informe, cfg)
        return

    await _responder_scan(context, msg, target, cfg, db)


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
    await _responder_scan(context, msg, msg, cfg, db)
    return True


async def _entregar(context, msg, texto: str, cfg) -> None:
    """En grupo: borra el comando y contesta al PRIVADO del admin.

    Un informe de «esto lo habría baneado» no pinta nada en el grupo, y además
    obligaba al admin a borrarlo a mano después. Igual que hace /scanuser.
    """
    from telegram.error import TelegramError
    en_grupo = bool(msg and msg.chat and msg.chat.type in ("group", "supergroup"))
    if not en_grupo:
        await msg.reply_text(texto, parse_mode="HTML", disable_web_page_preview=True)
        return
    try:
        await msg.delete()
    except TelegramError:
        pass
    destino = cfg.admin_notify_chat_id or cfg.admin_user_id
    try:
        await context.bot.send_message(chat_id=destino, text=texto, parse_mode="HTML",
                                       disable_web_page_preview=True)
    except TelegramError:
        # Un informe que no llega no sirve de nada: mejor en el grupo que perderlo.
        await context.bot.send_message(chat_id=msg.chat_id, text=texto,
                                       parse_mode="HTML", disable_web_page_preview=True)


async def _responder_scan(context, msg, target, cfg: Config, db: DB) -> None:
    """Corre los detectores sobre `target` y contesta el informe a `msg`.

    Si `target` es una HISTORIA, primero se intenta recuperar su texto por MTProto,
    igual que hace la moderación. Sin eso el diagnóstico seria incoherente: el bot
    sabria cazarla en el grupo pero al preguntarle por ella diria que no puede leerla.
    """
    leido = None
    if getattr(target, "story", None) is not None:
        leido = await story_reader.leer_caption(context, target.story)
        if leido is not None:
            texto, ents = leido
            target = story_reader.MensajeConTextoDeHistoria(target, texto, ents)
    _limpio, _trucos = desofuscar.para_detectores(target)
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
        comad_det.check(_limpio, is_first_msg=True),
        # Faltaba: el /scan no corría investment_scam, así que un testimonio de
        # estafa salía como «no se detectaría» aunque el bot sí lo cazara.
        invscam_det.check(_limpio, is_first_msg=True),
        emoji_det.check(target, is_first_msg=True),
        offplat_det.check(_limpio, is_first_msg=True),
        fwd_det.check(target, is_first_msg=True, seconds_since_first_seen=0.0),
    ]
    real = [h for h in hits if h]
    es_historia = getattr(target, "story", None) is not None

    lines = [t("scan.header"), ""]
    lines += _structure(target)
    # Si el texto venía camuflado hay que decirlo: si no, el admin ve que salta
    # `commercial_ad` sobre un mensaje que en pantalla no se parece a lo que dice
    # el motivo, y parece un error del bot cuando es justo lo contrario.
    if _trucos:
        lines.append(t("scan.disfraz",
                       trucos=", ".join(t(f"scan.disfraz.{x}") for x in _trucos)))
    lines.append("")
    if real:
        total = sum(h.score for h in real)
        lines.append(t("scan.detected", n=len(real), total=total))
        for h in sorted(real, key=lambda x: -x.score):
            lines.append(t("scan.hit", rule=h.rule, score=h.score, reason=_h.escape(h.reason)))
        lines.append("")
        lines.append(t("scan.trust_note"))
    elif not es_historia:
        lines.append(t("scan.not_detected"))
        lines.append(t("scan.profile_note"))
    if es_historia:
        # El /scan solo corre detectores de CONTENIDO: `story_share` necesita saber
        # quién manda el mensaje (si es su primer mensaje, si el bot vio su entrada,
        # cuántos lleva escritos) y eso aquí no se sabe. En vez de callarlo, se
        # simulan los tres perfiles y se dice qué pasaría con cada uno, que es lo
        # que el admin quiere saber al preguntar por un mensaje raro.
        from .detectors import story_share as story_det
        from .scoring import decide as _decide
        contenido = sum(h.score for h in real)

        def _escenario(**kw):
            est = story_det.check(target, user_id=0, **kw)
            total = contenido + (est.score if est else 0)
            hits_falsos = [h for h in real]
            if est:
                hits_falsos = hits_falsos + [est]
            acc = _decide(hits_falsos, cfg.ban_score, cfg.kick_score, cfg.mute_score,
                          "ban", False).action if hits_falsos else "noop"
            return total, acc

        n1, a1 = _escenario(is_first_msg=True, bot_saw_join=True, msg_count=1)
        n2, a2 = _escenario(is_first_msg=False, bot_saw_join=False, msg_count=2)
        lines.append("")
        lines.append(t("scan.story_scenarios",
                       contenido=contenido,
                       e1=n1 - contenido, n1=n1, a1=t(f"scan.act.{a1}"),
                       e2=n2 - contenido, n2=n2, a2=t(f"scan.act.{a2}")))

    if es_historia and leido is None:
        # Va SIEMPRE que no se haya podido leer, dispare o no alguna regla: el
        # veredicto se habria emitido sin haber
        # leído el contenido. Decir «no dispararía ninguna regla» a secas sería
        # engañoso, porque el admin sí ve el texto en su pantalla y daría por bueno
        # un análisis que el bot no ha podido hacer.
        lines.append("")
        lines.append(t("scan.story_blind"))

    await _entregar(context, msg, "\n".join(lines), cfg)
