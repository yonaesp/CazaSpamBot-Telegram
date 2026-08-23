"""Señales adicionales del perfil de un usuario vía Telethon.

Reusa el cliente Telethon ya inicializado en SpamReporter para no abrir
una segunda sesión. Devuelve count de fotos, fecha de la más antigua y más
reciente, y una heurística de "probable real / sospechoso / bot" basada en
la edad de la foto más antigua.
"""
from __future__ import annotations

from . import fechas
import asyncio
import datetime as _dt
import logging
from dataclasses import dataclass, field
from typing import Optional

from .i18n import t

log = logging.getLogger(__name__)

# Topes de tiempo. Esto NO es cosmético: `fetch()` se llama en la ruta caliente
# (cada entrada al grupo, y en varios caminos de `on_message`), y PTB procesa los
# updates DE UNO EN UNO, así que cada segundo aquí es un segundo en el que el bot
# no modera nada más.
#
# Sin tope, el peor caso era abierto por dos motivos que se suman:
#   1. `_resolve_entity` reintenta 3 veces con 1,5 s de espera entre intentos.
#      Medido con un cliente que falla al instante: **4,3 s** de reloj, íntegros
#      de `asyncio.sleep`, cada vez que una entidad no se resuelve.
#   2. Ante un FloodWait, Telethon **duerme sola hasta 60 s y no lanza excepción**
#      (lo mismo que ya obligó a poner topes en `story_reader` y `photos_batch`).
#      Y aquí hay hasta seis llamadas encadenadas.
#
# Con esto, lo peor que puede pasar son `_TIMEOUT_TOTAL_S` segundos y un None, que
# es un valor que TODOS los que llaman ya saben tratar («no lo sé», nunca «está
# limpio»). El total se ha elegido por encima de los 4,3 s de los reintentos a
# propósito: recortar por debajo desactivaría en silencio la espera del race del
# join, que existe porque Telegram tarda 1-2 s en propagar una participación nueva.
_TIMEOUT_LLAMADA_S = 5.0
_TIMEOUT_TOTAL_S = 12.0


async def _con_tope(coro, que: str, user_id: int):
    """Ejecuta una llamada de Telethon con tope. Devuelve None si se pasa."""
    try:
        return await asyncio.wait_for(coro, _TIMEOUT_LLAMADA_S)
    except asyncio.TimeoutError:
        log.info("user_signals: %s tardó demasiado (user=%s)", que, user_id)
        return None


@dataclass
class UserSignals:
    user_id: int
    photo_count: int = 0
    oldest_photo: Optional[_dt.datetime] = None
    newest_photo: Optional[_dt.datetime] = None
    bio: Optional[str] = None
    is_premium: bool = False
    # Canal personal enlazado en el perfil (Telegram 2024). Es un escaparate
    # SEPARADO de la bio: un perfil con la bio vacía puede tener ahí un canal
    # entero de spam, y hasta ahora no lo mirábamos. Caso real: cuenta llamada
    # «Matthew», sin foto ni bio, con un canal chino de blanqueo de dinero.
    personal_channel_title: Optional[str] = None
    personal_channel_id: Optional[int] = None
    # La entidad `Channel` tal cual la devuelve Telegram, guardada para que
    # `channel_reader` pueda leer el canal SIN volver a resolverlo: resolver por
    # @username dispara `contacts.ResolveUsername`, la llamada más propensa a
    # FloodWait de todas. `repr=False` porque es un objeto de Telethon y no tiene
    # ninguna gracia que aparezca entero en un log.
    personal_channel_entity: object = field(default=None, repr=False, compare=False)

    @property
    def account_age_days(self) -> Optional[int]:
        if not self.oldest_photo:
            return None
        now = _dt.datetime.now(tz=self.oldest_photo.tzinfo)
        return (now - self.oldest_photo).days

    @property
    def verdict(self) -> str:
        """Devuelve un veredicto heurístico basado en señales objetivas."""
        if self.photo_count == 0:
            return t("signals.verdict_no_photo")
        age = self.account_age_days or 0
        if age > 365:
            return t("signals.verdict_old", days=age)
        if age > 90:
            return t("signals.verdict_mid", days=age)
        return t("signals.verdict_new", days=age)


async def _resolve_once(client, user_id: int, chat_id: Optional[int],
                        first_name: Optional[str] = None):
    """Un intento de resolver la entidad. Devuelve el User o None.

    Para usuarios RECIÉN llegados (no cacheados), `get_entity(user_id)` y
    `GetParticipantRequest(participant=user_id)` fallan LOCALMENTE porque
    Telethon no puede construir el InputPeer sin access_hash. El método
    fiable es `get_participants(chat, search=nombre)`: búsqueda server-side
    que devuelve el User con access_hash sin necesidad de caché previa.
    """
    # 1) get_participants con search por nombre (el más fiable para users nuevos)
    if chat_id is not None and first_name:
        try:
            parts = await _con_tope(
                client.get_participants(chat_id, search=first_name[:32], limit=15),
                "get_participants", user_id) or []
            for p in parts:
                if getattr(p, "id", None) == user_id:
                    return p
        except Exception as exc:  # noqa: BLE001
            log.debug("get_participants(search=%r) fallo: %s", first_name, exc)
    # 2) Vía el canal: GetParticipantRequest (funciona si el user ya está cacheado)
    if chat_id is not None:
        try:
            from telethon.tl.functions.channels import GetParticipantRequest
            channel = await _con_tope(client.get_entity(chat_id), "get_entity(chat)", user_id)
            if channel is None:
                raise TimeoutError("chat irresoluble")
            res = await _con_tope(
                client(GetParticipantRequest(channel=channel, participant=user_id)),
                "GetParticipant", user_id)
            for u in getattr(res, "users", None) or []:
                if getattr(u, "id", None) == user_id:
                    return u
        except Exception as exc:  # noqa: BLE001
            log.debug("GetParticipant user=%s chat=%s fallo: %s", user_id, chat_id, exc)
    # 3) get_entity directo (funciona si ya está en caché)
    try:
        return await _con_tope(client.get_entity(user_id), "get_entity(user)", user_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("get_entity(%s) fallo: %s", user_id, exc)
        return None


async def _resolve_entity(client, user_id: int, chat_id: Optional[int],
                          first_name: Optional[str] = None,
                          retries: int = 2, delay: float = 1.5):
    """Resuelve la entidad de un usuario poblando su access_hash, con reintentos.

    Un usuario RECIÉN llegado no está en la caché de Telethon Y Telegram puede
    tardar 1-2s en propagar la nueva participación. Reintentamos con delay para
    cubrir esa ventana (race del join).
    """
    for attempt in range(retries + 1):
        entity = await _resolve_once(client, user_id, chat_id, first_name)
        if entity is not None:
            if attempt > 0:
                log.info("user_signals: entity user=%s resuelta en intento %d", user_id, attempt + 1)
            return entity
        if attempt < retries:
            await asyncio.sleep(delay)
    log.warning(
        "user_signals: no se pudo resolver entity user=%s chat=%s tras %d intentos",
        user_id, chat_id, retries + 1,
    )
    return None


async def fetch(client, user_id: int, chat_id: Optional[int] = None,
                first_name: Optional[str] = None) -> Optional[UserSignals]:
    """Señales del perfil, o None si no se pueden obtener a tiempo.

    None significa «no lo sé», nunca «está limpio»: quien llama debe tratarlo como
    ausencia de información. Ver el tope de tiempo arriba y por qué existe.
    """
    if client is None:
        return None
    try:
        return await asyncio.wait_for(
            _fetch(client, user_id, chat_id, first_name), _TIMEOUT_TOTAL_S)
    except asyncio.TimeoutError:
        log.warning("user_signals: se agotó el tiempo total con user=%s (%.0fs)",
                    user_id, _TIMEOUT_TOTAL_S)
        return None


async def _fetch(client, user_id: int, chat_id: Optional[int] = None,
                 first_name: Optional[str] = None) -> Optional[UserSignals]:
    if client is None:
        return None
    try:
        sig = UserSignals(user_id=user_id)
        entity = await _resolve_entity(client, user_id, chat_id, first_name)
        if entity is None:
            return None
        # Fotos: get_profile_photos devuelve Photo[] con .date
        try:
            photos = await _con_tope(
                client.get_profile_photos(entity, limit=20), "get_profile_photos", user_id)
            sig.photo_count = len(photos) if photos else 0
            if photos:
                dates = [p.date for p in photos if getattr(p, "date", None)]
                if dates:
                    sig.oldest_photo = min(dates)
                    sig.newest_photo = max(dates)
        except Exception as exc:  # noqa: BLE001
            log.debug("get_profile_photos %s fallo: %s", user_id, exc)
        # Bio: get_full_user sobre la entidad ya resuelta
        try:
            from telethon.tl.functions.users import GetFullUserRequest
            full = await _con_tope(
                client(GetFullUserRequest(entity)), "GetFullUser", user_id)
            if full is None:
                raise TimeoutError("GetFullUser sin respuesta")
            sig.bio = (full.full_user.about or "").strip()[:300] or None
            # El canal personal viene en full_user; su TÍTULO hay que buscarlo en
            # full.chats, que trae las entidades relacionadas.
            ch_id = getattr(full.full_user, "personal_channel_id", None)
            if ch_id:
                sig.personal_channel_id = ch_id
                ch = next((c for c in (full.chats or []) if getattr(c, "id", None) == ch_id), None)
                titulo = (getattr(ch, "title", "") or "").strip()
                sig.personal_channel_title = titulo[:200] or None
                # Se guarda la entidad, no solo el título: es lo que permite
                # después leer lo que PUBLICA el canal sin pagar un ResolveUsername.
                sig.personal_channel_entity = ch
        except Exception as exc:  # noqa: BLE001
            log.debug("GetFullUser %s fallo: %s", user_id, exc)
        sig.is_premium = bool(getattr(entity, "premium", False))
        return sig
    except Exception as exc:
        log.warning("user_signals fetch user=%s exc: %s", user_id, exc)
        return None


def render_markup(sig: Optional[UserSignals]) -> str:
    """Renderiza las señales como bloque HTML para incluir en notificación."""
    if sig is None:
        return ""
    parts = [t("signals.profile", verdict=sig.verdict)]
    parts.append(t("signals.photos", count=sig.photo_count))
    if sig.oldest_photo:
        parts.append(t("signals.oldest_photo", date=fechas.dia(sig.oldest_photo, "%Y-%m-%d")))
    if sig.newest_photo and sig.newest_photo != sig.oldest_photo:
        parts.append(t("signals.newest_photo", date=fechas.dia(sig.newest_photo, "%Y-%m-%d")))
    if sig.is_premium:
        parts.append(t("signals.premium"))
    if sig.bio:
        import html as _html
        parts.append(t("signals.bio", bio=_html.escape(sig.bio)))
    return " · ".join(parts[:4]) + ("\n" + parts[4] if len(parts) > 4 else "")
