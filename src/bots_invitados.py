"""Bots ajenos: el bot que escribe en un grupo sin que lo haya metido un admin.

Regla del admin (5-nov-2026): un bot solo puede escribir en un grupo moderado si lo
añadió un administrador. Cualquier otro se banea y su mensaje se borra:
- **Al entrar** (`handlers.on_chat_member`): un bot añadido por alguien que no es
  admin se banea en el acto. Lo añadido por un admin se queda.
- **Al escribir**: un bot que no es miembro del grupo (un «bot invitado») se banea.
  Uno que es miembro ya pasó por la puerta (o estaba antes de la regla) y sigue la
  ruta de bots de siempre (L40).

Los «bots invitados» son de la Bot API 10.0: una persona escribe @algobot en un
grupo donde ese bot NO está y el bot contesta allí mismo, con su propio mensaje. No
entra en el grupo ni deja rastro en el registro de administración. Telegram enlaza la
respuesta con quien lo llamó (`Message.guest_bot_caller_user`; en MTProto,
`guestchat_via_from`). No hay ningún permiso de grupo que lo impida.

Caso real (5-nov-2026, Domótica/Alexa): una cuenta nueva escribió «@xcb1cv5fdbot
@dsfsfds56bot @cxvxcrfdsfbot». El bot la baneó en 1 s por mencionar cuentas de fuera,
pero las llamadas ya estaban hechas: dos de esos bots contestaron a los 3 y a los 9 s
con el mismo anuncio en chino (billetes falsos, prostitución) y diez botones. La sonda
que limpia tras un ban borró el primero y ya había parado cuando llegó el segundo, que
se quedó seis horas en el grupo.

Tres vías, porque no está comprobado que la Bot API le entregue a un bot los mensajes
de un bot invitado:
1. **Bot API** (ruta de bots de `handlers`), si los entrega.
2. **La cuenta secundaria** (`telethon_bridge`): mira los mensajes nuevos de bots en
   los grupos moderados, por si la Bot API no los entrega (decisión del admin).
3. **Pasada tardía de la sonda**: tras banear a alguien cuyo mensaje mencionaba bots,
   vuelve a mirar y retira lo que hayan publicado esos bots.
`marcar` evita que dos vías actúen sobre el mismo mensaje.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import OrderedDict
from typing import Awaitable, Callable

from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

log = logging.getLogger("antispam")

# Cuándo vuelve a pasar la sonda tras la limpieza normal (segundos, acumulativos).
# Medido el 5-nov: las respuestas llegaron a los 3 y a los 9 s de la llamada; la
# limpieza normal pasa a los ~3 s del ban. Con 8 + 25 se cubren ~40 s.
ESPERAS_S: tuple[float, ...] = (8.0, 25.0)
MAX_PROBE = 10          # ids que mira cada pasada
_FALLOS_SEGUIDOS = 4    # ids que no existen (borrados o aún no escritos) antes de parar

# Telegram obliga a que el usuario de un bot acabe en «bot». 5-32 caracteres,
# empieza por letra.
_MENCION_BOT_RE = re.compile(r"(?<![\w@])@([a-z][a-z0-9_]{1,28}bot)(?!\w)", re.IGNORECASE)

Actuar = Callable[[int, object, str], Awaitable[None]]

# Remitentes que pone Telegram y no son bots de nadie: @GroupAnonymousBot (admin
# anónimo), @Channel_Bot (mensaje en nombre de un canal) y 777000 (Telegram, el
# reenvío automático del canal vinculado). No son miembros y nunca se tocan.
REMITENTES_DE_TELEGRAM = frozenset({1087968824, 136817688, 777000})


def mencionados(texto: str | None) -> set[str]:
    """Los @ de bots que aparecen en el texto, en minúsculas y sin la @."""
    return {m.group(1).lower() for m in _MENCION_BOT_RE.finditer(texto or "")}


def llamante(msg) -> int | None:
    """Quién llamó al bot invitado que publica este mensaje, o None si no lo es."""
    u = getattr(msg, "guest_bot_caller_user", None)
    uid = getattr(u, "id", None)
    return uid if isinstance(uid, int) else None


async def _es_miembro(bot, chat_id: int, user_id: int) -> bool:
    """True si el bot está en el grupo (o no se puede saber: lado seguro, no se toca)."""
    try:
        m = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramError as exc:
        texto = str(exc).lower()
        return not ("not found" in texto or "participant_id_invalid" in texto
                    or "user not participant" in texto)
    return m.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)


# Si un bot es miembro cambia poco: se recuerda 10 min. Un bot de la casa (el de
# warns) escribe a menudo y no puede costar un getChatMember por mensaje.
_MIEMBRO_TTL_S = 600
_MIEMBRO_MAX = 500
_miembro_cache: dict[tuple[int, int], tuple[float, bool]] = {}


async def es_miembro(bot, chat_id: int, bot_id: int) -> bool:
    """`_es_miembro` con caché. Lo que no se pudo saber no se guarda."""
    clave = (chat_id, bot_id)
    dato = _miembro_cache.get(clave)
    if dato and time.time() - dato[0] < _MIEMBRO_TTL_S:
        return dato[1]
    res = await _es_miembro(bot, chat_id, bot_id)
    if len(_miembro_cache) >= _MIEMBRO_MAX:
        _miembro_cache.pop(next(iter(_miembro_cache)))
    _miembro_cache[clave] = (time.time(), res)
    return res


def olvidar(chat_id: int, bot_id: int) -> None:
    """Tras banear o al entrar, lo recordado sobre ese bot ya no vale."""
    _miembro_cache.pop((chat_id, bot_id), None)


# Mensajes ya tratados: la Bot API y la cuenta secundaria pueden ver el mismo.
_ACTUADOS_MAX = 500
_actuados: OrderedDict[tuple[int, int], None] = OrderedDict()


def marcar(chat_id: int, message_id: int) -> bool:
    """True la primera vez que se pide actuar sobre ese mensaje; False las demás."""
    clave = (chat_id, message_id)
    if clave in _actuados:
        return False
    _actuados[clave] = None
    if len(_actuados) > _ACTUADOS_MAX:
        _actuados.popitem(last=False)
    return True


async def barrer(bot, chat_id: int, admin_dm: int, desde_id: int, bots: set[str],
                 actuar: Actuar, *, propio_id: int | None = None,
                 esperas: tuple[float, ...] = ESPERAS_S, max_probe: int = MAX_PROBE) -> int:
    """Pasadas tardías de la sonda: retira lo que publicaron los bots mencionados.

    Identifica al autor reenviando cada id al privado del admin (la copia se borra
    siempre), como la limpieza normal. Solo actúa sobre un mensaje cuyo autor es uno
    de `bots` y no es miembro del grupo; `actuar(id, autor, texto)` hace el resto.
    Devuelve cuántos encontró. Nunca lanza.
    """
    if not bots or not admin_dm or admin_dm <= 0:
        return 0
    vistos: set[int] = set()
    encontrados = 0
    for espera in esperas:
        await asyncio.sleep(espera)
        fallos = 0
        for probe_id in range(desde_id + 1, desde_id + max_probe + 1):
            if probe_id in vistos:
                continue
            await asyncio.sleep(0.3)
            try:
                sent = await bot.forward_message(chat_id=admin_dm, from_chat_id=chat_id,
                                                 message_id=probe_id, disable_notification=True)
            except TelegramError as exc:
                if "not found" in str(exc).lower():
                    fallos += 1
                    if fallos >= _FALLOS_SEGUIDOS:
                        break
                continue
            except Exception as exc:  # noqa: BLE001
                log.debug("bots_invitados: sonda %s falló: %s", probe_id, exc)
                continue
            fallos = 0
            vistos.add(probe_id)
            autor = getattr(getattr(sent, "forward_origin", None), "sender_user", None)
            texto = getattr(sent, "text", None) or getattr(sent, "caption", None) or ""
            try:
                await bot.delete_message(chat_id=admin_dm, message_id=sent.message_id)
            except TelegramError:
                pass
            usuario = (getattr(autor, "username", None) or "").lower()
            if (autor is None or not getattr(autor, "is_bot", False) or usuario not in bots
                    or autor.id == propio_id):
                continue
            if await es_miembro(bot, chat_id, autor.id):
                log.info("bots_invitados: @%s es miembro de %s, no se toca", usuario, chat_id)
                continue
            if not marcar(chat_id, probe_id):
                continue
            encontrados += 1
            log.info("bots_invitados: msg=%s de @%s (id=%s) en %s, llamado por un baneado",
                     probe_id, usuario, autor.id, chat_id)
            try:
                await actuar(probe_id, autor, texto)
            except Exception as exc:  # noqa: BLE001 — una pasada no tumba la siguiente
                log.warning("bots_invitados: no se pudo actuar sobre msg=%s: %s", probe_id, exc)
    return encontrados
