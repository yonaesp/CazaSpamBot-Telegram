"""La cuenta secundaria no entra en grupos ajenos (L59, 8-nov-2026).

Telethon trabaja con una cuenta de persona que es admin en los grupos. Con la
privacidad que Telegram trae de serie («¿Quién puede añadirme a grupos? Todos»),
cualquiera puede meterla en un grupo: un grupo de spam la luciría de escaparate y
estar dentro le resta reputación, que es la que respalda los reportes a Telegram.
Medido el 8-nov-2026: la de este bot estaba en «Todos».

Dos guardas, al arrancar y cada 24 h (`vigilar_job`):
1. Privacidad: si está en «Todos», se deja en «Mis contactos» (decisión del admin,
   8-nov: la opción de serie de Telegram, sin excepciones que haya que explicar).
   Cualquier otra elección la tomó alguien a propósito y se respeta.
2. Grupos: un grupo o canal donde no está el bot y al que la metió otra persona
   (ni el admin, ni un contacto, ni ella misma con un enlace o una solicitud, ni
   creado por ella) se abandona y se avisa al admin. Si no se sabe quién la metió,
   no se toca: un grupo legítimo perdido es peor que un grupo de spam un día más.

Al iniciar sesión (`scripts/telethon_login confirm`, o `privacidad`), quien instala
ve además la privacidad que importa a una cuenta de moderación (`AJUSTES`) y se le
ofrece corregirla de una vez (`revisar_e_informar`).

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

ETIQUETA = {"todos": "Todos", "contactos": "Mis contactos", "nadie": "Nadie"}


@dataclass(frozen=True)
class Ajuste:
    clave: str        # nombre del InputPrivacyKey de Telethon
    nombre: str       # como lo llama la app en Ajustes ▸ Privacidad y seguridad
    recomendado: str  # 'contactos' | 'nadie'
    porque: str


# Lo único que se corrige solo es el primero; los demás, solo si quien instala dice que sí.
AJUSTES: tuple[Ajuste, ...] = (
    Ajuste("InputPrivacyKeyChatInvite", "Grupos (quién puede añadirme)", "contactos",
           "un grupo de spam la luciría de escaparate y le restaría reputación para reportar"),
    Ajuste("InputPrivacyKeyPhoneNumber", "Número de teléfono (quién lo ve)", "nadie",
           "es admin en tus grupos y cualquiera de sus miembros vería su número"),
    Ajuste("InputPrivacyKeyPhoneCall", "Llamadas", "contactos",
           "las redes de spam también llaman"),
)
GRUPOS = AJUSTES[0]


def _abierta(reglas: list[Any]) -> bool:
    """«Todos», también «Todos menos…»: lo único que se corrige."""
    from telethon.tl.types import PrivacyValueAllowAll
    return any(isinstance(r, PrivacyValueAllowAll) for r in reglas)


def describir(reglas: list[Any]) -> str:
    """Como lo enseña la app: Todos, Mis contactos o Nadie, y si lleva excepciones."""
    nombres = {type(r).__name__ for r in reglas}
    base = ("Todos" if "PrivacyValueAllowAll" in nombres
            else "Mis contactos" if "PrivacyValueAllowContacts" in nombres else "Nadie")
    sueltas = nombres - {"PrivacyValueAllowAll", "PrivacyValueAllowContacts",
                         "PrivacyValueDisallowAll"}
    return base + (" (con excepciones)" if sueltas else "")


async def _reglas(client: Any, aj: Ajuste) -> list[Any] | None:
    """Las reglas actuales de un ajuste; None si no se pudieron leer."""
    from telethon.tl import types
    from telethon.tl.functions.account import GetPrivacyRequest
    try:
        return list((await client(GetPrivacyRequest(getattr(types, aj.clave)()))).rules)
    except Exception as exc:  # noqa: BLE001 - FloodWait, red...
        log.warning("cuenta secundaria: no se pudo leer «%s»: %s", aj.nombre, exc)
        return None


async def leer_privacidad(client: Any) -> list[tuple[Ajuste, list[Any] | None]]:
    """Las reglas actuales de cada ajuste de `AJUSTES`."""
    return [(aj, await _reglas(client, aj)) for aj in AJUSTES]


async def poner(client: Any, aj: Ajuste) -> bool:
    """Deja el ajuste en su valor recomendado, sin excepciones."""
    from telethon.tl import types
    from telethon.tl.functions.account import SetPrivacyRequest
    valor = (types.InputPrivacyValueAllowContacts() if aj.recomendado == "contactos"
             else types.InputPrivacyValueDisallowAll())
    try:
        await client(SetPrivacyRequest(getattr(types, aj.clave)(), [valor]))
    except Exception as exc:  # noqa: BLE001
        log.warning("cuenta secundaria: no se pudo cambiar «%s»: %s", aj.nombre, exc)
        return False
    log.info("cuenta secundaria: «%s» pasa a %s", aj.nombre, ETIQUETA[aj.recomendado])
    return True


async def cerrar_privacidad(client: Any) -> str:
    """Si cualquiera puede meterla en grupos, lo deja en «Mis contactos»."""
    reglas = await _reglas(client, GRUPOS)
    if reglas is None:
        return ERROR
    if not _abierta(reglas):
        return YA_CERRADA
    return CERRADA if await poner(client, GRUPOS) else ERROR


async def revisar_e_informar(client: Any, corregir: bool | None,
                             escribir: Callable[[str], Any] = print,
                             preguntar: Callable[[str], str] | None = None) -> int:
    """Para quien instala: enseña la privacidad y ofrece corregir lo abierto a todos.

    `corregir`: True corrige sin preguntar, False solo informa y None pregunta con
    `preguntar` (sin él, informa y dice el comando). Devuelve 1 si algo falló.
    """
    estado = await leer_privacidad(client)
    escribir("\nPrivacidad de la cuenta secundaria:")
    abiertos, fallos = [], 0
    for aj, reglas in estado:
        if reglas is None:
            escribir(f"  ❓ {aj.nombre}: no se pudo leer")
            fallos += 1
        elif _abierta(reglas):
            escribir(f"  ⚠️  {aj.nombre}: {describir(reglas)} → recomendado "
                     f"«{ETIQUETA[aj.recomendado]}»: {aj.porque}")
            abiertos.append(aj)
        else:
            escribir(f"  ✅ {aj.nombre}: {describir(reglas)}")
    if not abiertos:
        return 1 if fallos else 0
    comando = "python -m scripts.telethon_login privacidad --corregir"
    if corregir is None:
        if preguntar is None:
            escribir(f"Para corregirlo: {comando}")
            return 1 if fallos else 0
        try:
            resp = preguntar("¿Lo corrijo ahora? (S/n): ").strip().lower()
        except EOFError:
            resp = "n"
        corregir = resp in ("", "s", "si", "sí", "y", "yes")
    if not corregir:
        escribir(f"Sin cambios. Cuando quieras: {comando}")
        return 1 if fallos else 0
    for aj in abiertos:
        ok = await poner(client, aj)
        fallos += not ok
        escribir(f"  {'✅' if ok else '❌'} {aj.nombre} → {ETIQUETA[aj.recomendado]}")
    if GRUPOS in abiertos:
        escribir("Para meterla tú en un grupo nuevo: en esa cuenta, guarda la tuya en sus "
                 "contactos. Se cambia en la app: Ajustes ▸ Privacidad y seguridad.")
    return 1 if fallos else 0


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
    privacidad = await cerrar_privacidad(client)
    if privacidad == CERRADA:
        avisos.append(t("cuenta2.privacidad_cerrada"))

    from .handlers import _se_modera
    del_bot = {r["chat_id"] for r in db.all_chats()}
    contactos = await _contactos(client)
    try:
        yo = (await client.get_me()).id
    except Exception as exc:  # noqa: BLE001
        log.warning("cuenta secundaria: get_me falló: %s", exc)
        yo = None
    salidas: int | str = "sin mirar (faltan contactos o get_me)"
    if contactos is not None and yo is not None:
        salidas = 0
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
            salidas += 1
            miembros = t("cuenta2.miembros", n=g.miembros) if g.miembros else ""
            avisos.append(t("cuenta2.salida", grupo=html.escape(g.titulo[:80]),
                            miembros=miembros, quien=await _nombre_de(client, g.invito)))

    # Una línea por pasada: un vigilante que no deja rastro no se sabe si corrió.
    log.info("cuenta secundaria: pasada hecha; privacidad de grupos %s; grupos ajenos dejados: %s",
             privacidad, salidas)
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
