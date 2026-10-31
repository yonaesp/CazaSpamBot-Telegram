"""Barrido semanal de bios de los miembros que el bot no tiene vistos.

El bot mira el perfil al entrar, en el repaso de los 7 días siguientes y con el
primer mensaje. A quien entró antes que el bot, o cuya entrada no le llegó, no lo
mira nunca. En el barrido a mano del 31-oct-2026 eran 1.982 de 6.534 miembros, y
entre ellos había una red de 5 cuentas «my blog 18+» (dentro desde sep-2025) y la
quinta cuenta de la red de Helen, que entró el 29-oct sin dejar rastro (L49).

La bio solo sale de `GetFullUser`, persona a persona: listar 1.000 miembros cuesta
0,7 s, pero cada bio es una llamada a la cuenta secundaria. Por eso:
- solo se lee a quien no está en `seen_users` ni se ha leído ya (`barrido_bios`),
- como mucho `MAX_POR_PASADA` por semana y con `PAUSA_S` entre una y otra (en
  6.534 llamadas a 1-2 s hubo un solo FloodWait, de 6 s),
- un FloodWait que Telethon no espera solo (más de 60 s) corta la pasada, y lo que
  falta sigue la semana siguiente.

No banea: lo que caza `bio_spam` va al privado con los botones de la revisión de
sospechosos (✅ Permitir / 🔨 Banear). Son miembros de hace tiempo que no han
escrito, así que no corre prisa, y una acción masiva sin revisar no se hace nunca.
Una bio con enlace privado que no llega al umbral no se da por leída: la primera
cuenta de una red se queda en 55, y si la red crece, la semana siguiente salta.
"""
from __future__ import annotations

import asyncio
import html
import logging

from telegram import InlineKeyboardMarkup
from telegram.error import TelegramError

from . import enlaces, notify_prefs, verification
from .config import Config
from .db import DB
from .detectors import bio_spam
from .i18n import t

log = logging.getLogger(__name__)

# 400 lecturas a ~2 s son unos 15 minutos por semana. La primera vez hay unos
# 2.000 pendientes, que salen en cinco semanas; después, solo los que se le escapen
# al bot al entrar.
MAX_POR_PASADA = 400
PAUSA_S = 2.0


async def barrido_job(context) -> None:
    """Lee la bio de los miembros que el bot no conoce y avisa de lo que caza."""
    db: DB = context.bot_data["db"]
    cfg: Config = context.bot_data["cfg"]
    reporter = context.bot_data.get("reporter")
    client = reporter.get_client() if reporter else None
    if client is None:
        log.warning("barrido_bios: sin Telethon no se puede leer ninguna bio")
        return
    try:
        r = await barrer(context.bot, db, cfg, client)
    except Exception as exc:  # noqa: BLE001 — un trabajo de fondo nunca tumba el bot
        log.warning("barrido_bios: la pasada falló: %s", exc)
        return
    log.info("barrido_bios: %d bios leídas, %d avisos, %d pendientes para la próxima",
             r["leidas"], r["avisos"], r["pendientes"])


async def barrer(bot, db: DB, cfg: Config, client) -> dict[str, int]:
    """Una pasada. Devuelve cuántas bios leyó, cuántos avisos mandó y cuántas faltan."""
    from telethon.errors import FloodWaitError
    from telethon.tl.functions.users import GetFullUserRequest
    from telethon.tl.types import ChannelParticipantsAdmins

    from .handlers import _se_modera

    chats = {f["chat_id"]: f for f in db.all_chats() if _se_modera(db, cfg, f["chat_id"])}
    vistos = db.usuarios_conocidos() | db.bios_barridas()
    admins: set[int] = set()
    cola: dict[int, tuple[int, object]] = {}
    for chat_id in chats:
        try:
            async for a in client.iter_participants(chat_id, filter=ChannelParticipantsAdmins()):
                admins.add(a.id)
            async for u in client.iter_participants(chat_id):
                if not (u.bot or u.deleted or u.is_self or u.id in vistos or u.id in cola):
                    cola[u.id] = (chat_id, u)
        except Exception as exc:  # noqa: BLE001 — un grupo ilegible no para los demás
            log.warning("barrido_bios: no se pudo listar chat=%s: %s", chat_id, exc)
    pendientes = [(uid, chat_id, u) for uid, (chat_id, u) in cola.items()
                  if uid not in admins and not db.is_banned(uid)
                  and not db.is_whitelisted(chat_id, uid)]

    leidas = avisos = 0
    for uid, chat_id, u in pendientes[:MAX_POR_PASADA]:
        try:
            full = await client(GetFullUserRequest(u))
        except FloodWaitError as exc:
            log.warning("barrido_bios: FloodWait de %d s tras %d bios; sigue la semana que viene",
                        exc.seconds, leidas)
            break
        except Exception as exc:  # noqa: BLE001 — sin apuntarla, se reintenta la semana que viene
            log.debug("barrido_bios: no se pudo leer a %s: %s", uid, exc)
            continue
        leidas += 1
        bio = full.full_user.about or ""
        hit = bio_spam.check(bio, db=db, user_id=uid) if bio else None
        if hit:
            await _avisar(bot, db, cfg, chats[chat_id], u, bio, hit)
            avisos += 1
        if hit or not bio_spam.enlaces_privados(bio):
            db.marcar_bio_barrida(uid)
        await asyncio.sleep(PAUSA_S)
    return {"leidas": leidas, "avisos": avisos, "pendientes": len(pendientes) - leidas}


async def _avisar(bot, db: DB, cfg: Config, chat, u, bio: str, hit) -> None:
    """Privado al admin con la bio, el motivo y los botones de la revisión de sospechosos."""
    chat_id = chat["chat_id"]
    db.log_action(
        chat_id=chat_id, user_id=u.id, username=u.username, message_id=None,
        rule=hit.rule, action="noop", score=hit.score, mode=cfg.mode,
        payload={**hit.payload, "via": "barrido_bios", "would_be": "review"},
    )
    if not cfg.admin_notify_chat_id:
        return
    nombre = " ".join(p for p in (u.first_name, u.last_name) if p) or str(u.id)
    texto = t(
        "barrido.aviso_dm",
        persona=enlaces.al_perfil(u.id, html.escape(nombre), u.username),
        uid=u.id,
        grupo=enlaces.al_grupo(chat_id, html.escape(chat["title"] or str(chat_id)),
                               chat["username"]),
        bio=html.escape(bio[:300]),
        motivo=html.escape(hit.reason),
    )
    try:
        await bot.send_message(
            chat_id=cfg.admin_notify_chat_id, text=texto, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([verification._rv_decide_row(chat_id, u.id)]),
            disable_web_page_preview=True,
            disable_notification=notify_prefs.sin_sonido(db, importante=True),
        )
    except TelegramError as exc:
        log.warning("barrido_bios: no se pudo avisar de %s: %s", u.id, exc)
