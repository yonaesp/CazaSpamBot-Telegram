"""La cuenta secundaria no entra en grupos ajenos (L59, 8-nov-2026).

Telethon trabaja con una cuenta de persona que es admin en los grupos. Con la
privacidad que Telegram trae de serie («¿Quién puede añadirme a grupos? Todos»),
cualquiera puede meterla en un grupo: un grupo de spam la luciría de escaparate y
estar dentro le resta reputación, que es la que respalda los reportes a Telegram.
Medido el 8-nov-2026: la de este bot estaba en «Todos».

Dos guardas, al arrancar y cada 24 h (`vigilar_job`):
1. Privacidad: si está en «Todos», se cierra a sus contactos y al admin del bot.
   Cualquier otra elección la tomó alguien a propósito y se respeta.
2. Grupos: un grupo o canal donde no está el bot y al que la metió otra persona
   (ni el admin, ni un contacto, ni ella misma con un enlace o una solicitud, ni
   creado por ella) se abandona y se avisa al admin. Si no se sabe quién la metió,
   no se toca: un grupo legítimo perdido es peor que un grupo de spam un día más.

Nunca se une a nada ni lee mensajes: tres o cuatro llamadas al día.
"""
from __future__ import annotations

import asyncio
import html
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from telegram.error import TelegramError

from . import enlaces, notify_prefs
from .i18n import t

log = logging.getLogger(__name__)

CERRADA, YA_CERRADA, ERROR = "cerrada", "ya_cerrada", "error"
# El job diario y el alta en un grupo pueden coincidir: una pasada a la vez.
_UNA_A_LA_VEZ = asyncio.Lock()


async def cerrar_privacidad(client: Any, admin_id: int | None) -> str:
    """Si cualquiera puede meterla en grupos, lo cierra a sus contactos y al admin."""
    from telethon import utils
    from telethon.tl.functions.account import GetPrivacyRequest, SetPrivacyRequest
    from telethon.tl.types import (
        InputPrivacyKeyChatInvite,
        InputPrivacyValueAllowContacts,
        InputPrivacyValueAllowUsers,
        PrivacyValueAllowAll,
    )
    try:
        actual = await client(GetPrivacyRequest(InputPrivacyKeyChatInvite()))
    except Exception as exc:  # noqa: BLE001 - FloodWait, red...
        log.warning("cuenta secundaria: no se pudo leer quién puede meterla en grupos: %s", exc)
        return ERROR
    if not any(isinstance(r, PrivacyValueAllowAll) for r in actual.rules):
        return YA_CERRADA
    reglas: list[Any] = [InputPrivacyValueAllowContacts()]
    if admin_id:
        try:
            reglas.append(InputPrivacyValueAllowUsers(
                [utils.get_input_user(await client.get_input_entity(admin_id))]))
        except Exception as exc:  # noqa: BLE001 - el admin no está en su caché
            log.info("cuenta secundaria: el admin %s no se pudo resolver (%s); solo contactos",
                     admin_id, exc)
    try:
        await client(SetPrivacyRequest(InputPrivacyKeyChatInvite(), reglas))
    except Exception as exc:  # noqa: BLE001
        log.warning("cuenta secundaria: no se pudo cerrar quién puede meterla en grupos: %s", exc)
        return ERROR
    log.info("cuenta secundaria: «añadirme a grupos» pasa de Todos a contactos + admin")
    return CERRADA


@dataclass
class GrupoAjeno:
    chat_id: int
    titulo: str
    miembros: int | None
    invito: int
    entidad: Any


async def _quien_la_metio(client: Any, dialogo: Any, yo: int) -> tuple[int | None, bool]:
    """(quién la metió, si entró por solicitud propia); (None, False) si no se sabe."""
    try:
        if dialogo.is_channel:
            from telethon.tl.functions.channels import GetParticipantRequest
            from telethon.tl.types import InputPeerSelf
            p = (await client(GetParticipantRequest(dialogo.entity, InputPeerSelf()))).participant
        else:
            from telethon.tl.functions.messages import GetFullChatRequest
            full = await client(GetFullChatRequest(dialogo.entity.id))
            ps = full.full_chat.participants
            p = getattr(ps, "self_participant", None) or next(
                (x for x in getattr(ps, "participants", None) or [] if x.user_id == yo), None)
    except Exception as exc:  # noqa: BLE001
        log.info("cuenta secundaria: no sé quién la metió en %s: %s", dialogo.id, exc)
        return None, False
    return getattr(p, "inviter_id", None), bool(getattr(p, "via_request", False))


async def grupos_ajenos(client: Any, yo: int, de_confianza: set[int],
                        es_nuestro: Callable[[int], bool]) -> list[GrupoAjeno]:
    """Grupos y canales donde no está el bot y a los que la metió otra persona."""
    fuera: list[GrupoAjeno] = []
    async for d in client.iter_dialogs():
        e = d.entity
        if d.is_user or getattr(e, "left", False) or getattr(e, "creator", False):
            continue
        if getattr(e, "deactivated", False) or es_nuestro(d.id):
            continue
        invito, por_solicitud = await _quien_la_metio(client, d, yo)
        if invito is None or por_solicitud or invito == yo or invito in de_confianza:
            log.info("cuenta secundaria: está en %s (%r), entró %s; se deja", d.id,
                     getattr(e, "title", "")[:40],
                     "sin saber cómo" if invito is None else "por su cuenta o de mano de confianza")
            continue
        fuera.append(GrupoAjeno(d.id, getattr(e, "title", "") or "?",
                                getattr(e, "participants_count", None), invito, e))
    return fuera


async def _contactos(client: Any) -> set[int] | None:
    from telethon.tl.functions.contacts import GetContactIDsRequest
    try:
        return set(await client(GetContactIDsRequest(hash=0)))
    except Exception as exc:  # noqa: BLE001
        log.warning("cuenta secundaria: no se pudieron leer sus contactos: %s", exc)
        return None


async def _nombre_de(client: Any, user_id: int) -> str:
    try:
        u = await client.get_entity(user_id)
    except Exception:  # noqa: BLE001 - sin caché: el id a secas
        return enlaces.al_perfil(user_id, str(user_id))
    nombre = " ".join(p for p in (getattr(u, "first_name", None),
                                  getattr(u, "last_name", None)) if p) or str(user_id)
    return enlaces.al_perfil(user_id, html.escape(nombre), getattr(u, "username", None))


async def vigilar_job(context: Any) -> None:
    """Cierra la privacidad de grupos y saca a la cuenta de los grupos ajenos."""
    async with _UNA_A_LA_VEZ:
        await _vigilar(context)


async def _vigilar(context: Any) -> None:
    rep = context.bot_data.get("reporter")
    client = rep.get_client() if rep else None
    if client is None:
        return
    cfg, db = context.bot_data["cfg"], context.bot_data["db"]
    if cfg.shadow:
        log.info("cuenta secundaria: modo shadow, no se toca su privacidad ni sus grupos")
        return
    avisos: list[str] = []
    if await cerrar_privacidad(client, cfg.admin_user_id) == CERRADA:
        avisos.append(t("cuenta2.privacidad_cerrada"))

    from .handlers import _se_modera
    del_bot = {r["chat_id"] for r in db.all_chats()}
    contactos = await _contactos(client)
    try:
        yo = (await client.get_me()).id
    except Exception as exc:  # noqa: BLE001
        log.warning("cuenta secundaria: get_me falló: %s", exc)
        yo = None
    if contactos is not None and yo is not None:
        confianza = contactos | ({cfg.admin_user_id} if cfg.admin_user_id else set())
        ajenos = await grupos_ajenos(
            client, yo, confianza, lambda cid: cid in del_bot or _se_modera(db, cfg, cid))
        for g in ajenos:
            try:
                await client.delete_dialog(g.entidad)
            except Exception as exc:  # noqa: BLE001
                log.warning("cuenta secundaria: no pudo salir de %s: %s", g.chat_id, exc)
                continue
            log.info("cuenta secundaria: sale de %s (%r), la metió %s", g.chat_id,
                     g.titulo[:40], g.invito)
            miembros = t("cuenta2.miembros", n=g.miembros) if g.miembros else ""
            avisos.append(t("cuenta2.salida", grupo=html.escape(g.titulo[:80]),
                            miembros=miembros, quien=await _nombre_de(client, g.invito)))

    if not avisos or not cfg.admin_notify_chat_id:
        return
    try:
        await context.bot.send_message(
            chat_id=cfg.admin_notify_chat_id, text="\n\n".join(avisos), parse_mode="HTML",
            disable_web_page_preview=True,
            disable_notification=notify_prefs.sin_sonido(db, importante=False),
        )
    except TelegramError as exc:
        log.warning("cuenta secundaria: no se pudo avisar al admin: %s", exc)
