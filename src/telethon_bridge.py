"""Listener Telethon para eventos que Bot API no entrega.

Específicamente: cuando un usuario borra su propio mensaje, Telegram NO manda
update al bot. Telethon (cliente MTProto) sí recibe `UpdateDeleteMessages` /
`UpdateDeleteChannelMessages`. Este módulo escucha esos events y borra en
cascada los avisos del bot que respondieron a esos mensajes.
"""
from __future__ import annotations

import html as _h
import logging
import os
import time as _t
from typing import Any

from telegram import Bot
from telegram.error import TelegramError

from .db import DB
from .i18n import t

log = logging.getLogger(__name__)


def _marked_chat_id(telethon_chat_id: int) -> int:
    """Normaliza el chat_id de un evento Telethon al formato Bot API (-100…).

    Al handler MessageDeleted solo llega chat_id de CANALES/SUPERGRUPOS: los
    borrados en grupos básicos y PM vienen como UpdateDeleteMessages sin peer
    (chat_id None) y se filtran antes de llegar aquí. Por eso el destino es
    siempre un canal, cuyo formato Bot API es -100<id>.

    Robusto ante cualquier versión de Telethon:
      - Telethon moderno (>=1.20, aquí 1.43) ya devuelve el id MARCADO y negativo
        (-100…): se usa tal cual.
      - Telethon antiguo lo devuelve CRUDO y positivo: se le antepone -100.
    Idempotente: un id ya marcado (negativo) nunca se vuelve a marcar.
    """
    if telethon_chat_id < 0:
        return telethon_chat_id
    return int(f"-100{telethon_chat_id}")


def attach(client, bot: Bot, db: DB, context=None) -> None:
    """Registra los handlers de Telethon: MessageDeleted y cambios de nombre.

    `context` es opcional para no romper a quien llame con la firma antigua; sin
    él simplemente no se engancha el aviso de cambio de nombre.
    """
    try:
        from telethon import events
    except ImportError:
        log.warning("telethon no disponible para attach()")
        return

    if context is not None:
        _attach_cambio_de_nombre(client, events, context)

    @client.on(events.MessageDeleted)
    async def _on_deleted(event: Any) -> None:
        try:
            chat_id = event.chat_id
            if not chat_id:
                # Borrado en grupo básico/PM: Telethon no sabe de qué chat es.
                # No podemos actuar sin chat → salimos (no es un canal moderable).
                return
            full_chat_id = _marked_chat_id(chat_id)
            from . import admin_report as ar_mod
            for msg_id in event.deleted_ids:
                # 1) Cascade gentle_warnings (bot avisó a user, user borra → borrar aviso)
                bot_msg = db.pop_gentle_warning_by_user_msg(full_chat_id, msg_id)
                if bot_msg:
                    try:
                        await bot.delete_message(chat_id=full_chat_id, message_id=bot_msg)
                        log.info(
                            "gentle_warning cascada: borrado bot_msg=%s tras delete user_msg=%s en chat=%s",
                            bot_msg, msg_id, full_chat_id,
                        )
                    except TelegramError as exc:
                        log.debug("delete bot_msg fallo: %s", exc)
                # 2) Cascade admin_reports (admin borra msg reportado → borrar @admin + thanks)
                try:
                    await ar_mod.on_reported_message_deleted(bot, db, full_chat_id, msg_id)
                except Exception as exc:
                    log.warning("admin_report cascade exc: %s", exc)
            # 3) Notif manual delete: UN solo aviso por lote. Telegram entrega
            # los borrados de una tacada en un mismo update, y mandar un mensaje
            # por cada uno era confuso: el admin veía «se borró 1» cuando había
            # borrado ocho.
            try:
                await _notificar_borrados(client, bot, db, full_chat_id,
                                          list(event.deleted_ids))
            except Exception as exc:  # noqa: BLE001
                log.warning("notificar_borrados exc chat=%s: %s", full_chat_id, exc)
        except Exception as exc:
            log.warning("on_deleted exc: %s", exc)


def _bots_a_ignorar(bot: Bot) -> set:
    """Bots cuyos borrados NO son moderación y no merecen aviso (ruido):
    el propio bot, y los de automatización listados en `SKIP_DELETE_NOTIF_BOTS`
    (CSV de user_ids en `.env`). Ejemplo: un bot que reemplaza enlaces de Amazon
    por referidos borra y repone el mensaje; es su función normal.
    """
    own_id = getattr(bot, "id", None)
    extra = {
        int(x) for x in os.getenv("SKIP_DELETE_NOTIF_BOTS", "").replace(" ", "").split(",")
        if x.strip().lstrip("-").isdigit()
    }
    return ({own_id} if own_id else set()) | extra


def _borrados_por_el_bot(db: DB, chat_id: int, msg_ids: list[int]) -> set:
    """Los que el propio bot acaba de borrar moderando: de esos no se avisa."""
    if not msg_ids:
        return set()
    marcas = ",".join("?" * len(msg_ids))
    with db._cur() as c:
        filas = c.execute(
            f"SELECT DISTINCT message_id FROM moderation_log "
            f"WHERE chat_id=? AND message_id IN ({marcas}) AND ts > ? "
            f"AND action IN ('ban','kick','mute','delete')",
            (chat_id, *msg_ids, _t.time() - 60),
        ).fetchall()
    return {r["message_id"] for r in filas}


async def _quien_borro(client, chat_id: int, msg_ids: set):
    """(actor_info, actor_id) según el registro de administración del chat.

    Una SOLA pasada para todo el lote. Antes se recorría el admin_log una vez por
    mensaje: al borrar diez de golpe eran diez recorridos idénticos. Los borrados
    de una tacada son una misma acción, así que el actor es el mismo para todos.
    """
    try:
        entity = await client.get_entity(chat_id)
        async for entry in client.iter_admin_log(entity, limit=50, delete=True):
            action = getattr(entry, "action", None)
            borrado = getattr(action, "message", None) if action else None
            if borrado is None or getattr(borrado, "id", None) not in msg_ids:
                continue
            actor = getattr(entry, "user", None)
            if actor is None and getattr(entry, "user_id", None):
                actor = await client.get_entity(entry.user_id)
            if actor is not None:
                nombre = getattr(actor, "first_name", None) or "?"
                uname = getattr(actor, "username", None)
                aid = getattr(actor, "id", "?")
                tag = f"@{uname}" if uname else nombre
                return t("tb.actor_info", tag=_h.escape(tag), uid=aid), aid
            break
    except Exception as exc:  # noqa: BLE001
        log.debug("manual_delete admin_log lookup fallo chat=%s: %s", chat_id, exc)
    return "?", None


def _contenido_de(db: DB, chat_id: int, msg_id: int):
    """(autor_id, autor_nombre, texto) de un mensaje borrado, o None.

    OJO: `seen_users` guarda solo el ÚLTIMO mensaje de cada persona, así que de un
    lote de diez borrados normalmente solo uno tiene texto recuperable. Los demás
    NO se descartan: se listan por su id, que es justo lo que faltaba y confundía
    al admin («borré ocho y el bot me avisó de uno»).
    """
    with db._cur() as c:
        fila = c.execute(
            "SELECT user_id, first_name, last_msg_text FROM seen_users "
            "WHERE chat_id=? AND last_msg_id=?",
            (chat_id, msg_id),
        ).fetchone()
    if not fila or not fila["last_msg_text"]:
        return None
    return fila["user_id"], (fila["first_name"] or "?"), fila["last_msg_text"]


async def _notificar_borrados(client, bot: Bot, db: DB, chat_id: int,
                              msg_ids: list[int]) -> None:
    """UN aviso por lote de borrados, con TODOS los mensajes mencionados.

    Antes se mandaba un aviso por mensaje y solo salían los que tenían texto
    guardado, o sea casi siempre uno: el admin borraba ocho y recibía un aviso de
    uno, sin manera de saber que faltaban siete.

    Se sigue callando cuando no hay NADA que enseñar (ningún texto recuperable):
    una lista de ids pelados no informa de nada y sería ruido puro.
    """
    ids = [m for m in msg_ids if m]
    if not ids:
        return
    ya_nuestros = _borrados_por_el_bot(db, chat_id, ids)
    ids = [m for m in ids if m not in ya_nuestros]
    if not ids:
        log.debug("manual_delete: el lote de chat=%s lo borró el propio bot", chat_id)
        return

    actor_info, actor_id = await _quien_borro(client, chat_id, set(ids))
    if actor_id in _bots_a_ignorar(bot):
        log.debug("manual_delete skip: borrado por bot conocido %s", actor_id)
        return

    # Actor desconocido = casi siempre el propio autor borrando lo suyo
    # (el admin_log solo registra borrados de admins). Para algunos es ruido.
    from . import notify_prefs
    if actor_id is None:
        env_default = os.getenv("NOTIFY_SELF_DELETES", "false").strip().lower() in (
            "1", "true", "yes", "on")
        if not notify_prefs.is_enabled(db, "self_delete", env_default):
            log.debug("manual_delete skip: self-delete y avisos silenciados")
            return

    admin_id_env = os.getenv("ADMIN_USER_ID", "0")
    try:
        admin_id = int(admin_id_env)
    except ValueError:
        admin_id = 0
    if admin_id <= 0:
        return

    chat_title = str(chat_id)
    with db._cur() as c:
        fila = c.execute("SELECT title FROM bot_chats WHERE chat_id=?", (chat_id,)).fetchone()
        if fila and fila["title"]:
            chat_title = fila["title"]

    con_texto, sin_texto = [], []
    for m in sorted(ids):
        datos = _contenido_de(db, chat_id, m)
        (con_texto if datos else sin_texto).append((m, datos))
    if not con_texto:
        # Nada que enseñar: una lista de ids pelados no informa de nada.
        log.debug("manual_delete: %d borrados en chat=%s sin contenido guardado",
                  len(ids), chat_id)
        return

    def _estado_de(author_id):
        if not author_id:
            return ""
        try:
            with db._cur() as c:
                row = c.execute(
                    "SELECT 1 FROM banned_users WHERE user_id=? AND revoked_at IS NULL",
                    (author_id,),
                ).fetchone()
            return t("tb.del_state_banned") if row else t("tb.del_state_in_group")
        except Exception:  # noqa: BLE001
            return ""

    if len(ids) == 1:
        # Uno solo: el aviso de siempre, que ya estaba bien.
        msg_id, datos = con_texto[0]
        author_id, author_name, texto = datos
        enlace = (f'<a href="tg://user?id={author_id}">{_h.escape(author_name)}</a>'
                  if author_id else _h.escape(author_name))
        notif = t("tb.manual_delete", chat=_h.escape(chat_title), actor=actor_info,
                  author_link=enlace, author_id=author_id or "?",
                  state=_estado_de(author_id), msg_id=msg_id,
                  content=_h.escape(texto[:600]))
    else:
        partes = [t("tb.manual_delete_multi", chat=_h.escape(chat_title),
                    actor=actor_info, n=len(ids))]
        # Se reparte el espacio: Telegram corta en 4096 caracteres y perder el
        # final del aviso sería volver al problema de origen.
        por_msg = max(120, 2800 // max(1, len(con_texto)))
        for msg_id, datos in con_texto:
            author_id, author_name, texto = datos
            enlace = (f'<a href="tg://user?id={author_id}">{_h.escape(author_name)}</a>'
                      if author_id else _h.escape(author_name))
            partes.append(t("tb.manual_delete_item", msg_id=msg_id, author_link=enlace,
                            author_id=author_id or "?", state=_estado_de(author_id),
                            content=_h.escape(texto[:por_msg])))
        if sin_texto:
            partes.append(t("tb.manual_delete_sin_texto",
                            n=len(sin_texto),
                            ids=", ".join(str(m) for m, _ in sin_texto[:30])))
        notif = "\n".join(partes)[:4000]

    kb = None
    if actor_id is None:
        from telegram import InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([[notify_prefs.mute_button("self_delete")]])
    try:
        await bot.send_message(chat_id=admin_id, text=notif, parse_mode="HTML",
                               reply_markup=kb, disable_web_page_preview=True)
    except TelegramError as exc:
        log.debug("manual_delete notif send fallo: %s", exc)


def _attach_cambio_de_nombre(client, events, context) -> None:
    """Escucha `updateUserName`: alguien se ha cambiado el nombre AHORA.

    Por qué esto existe: el truco de esta red es entrar con un nombre que pasa
    los filtros y ponerse el de verdad justo antes de escribir. El repaso
    periódico lo caza, pero con hasta 15 minutos de retraso; este update lo caza
    en segundos.

    **La Bot API no entrega nada de esto.** Sus `chat_member` son cambios de
    ESTADO (entrar, salir, ban, promote); un cambio de perfil no genera ninguno.
    Solo MTProto tiene `updateUserName`.

    Y aquí va la parte honesta: la documentación oficial **no dice para qué
    usuarios se entrega** ese update, así que esto es a la vez defensa y
    experimento. Si Telegram lo manda para miembros de un supergrupo, cerramos
    el hueco de raíz; si no lo manda, este handler no se dispara jamás y el
    barrido periódico sigue siendo la defensa. No se pierde nada por tenerlo, y
    el log lo dirá.

    El update **no decide nada**: solo invalida las cachés y lanza la revisión
    normal, para que no haya dos varas de medir.
    """
    try:
        from telethon.tl.types import UpdateUserName
    except ImportError:
        log.warning("telethon sin UpdateUserName: no se vigilan cambios de nombre")
        return

    from . import recien_llegados

    @client.on(events.Raw(UpdateUserName))
    async def _on_user_name(update: Any) -> None:  # noqa: ANN401
        try:
            user_id = getattr(update, "user_id", None)
            if not user_id:
                return
            nombre = " ".join(
                p for p in (getattr(update, "first_name", None),
                            getattr(update, "last_name", None)) if p
            )
            log.info("updateUserName: user=%s se ha puesto %r", user_id, nombre[:60])
            await recien_llegados.revisar_ahora(context, user_id, motivo="cambio de nombre")
        except Exception as exc:  # noqa: BLE001 — un handler suelto jamás tumba el bot
            log.warning("updateUserName handler exc: %s", exc)

    log.info("Telethon: vigilando también los cambios de nombre (updateUserName)")
