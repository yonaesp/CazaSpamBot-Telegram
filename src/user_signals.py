"""Señales adicionales del perfil de un usuario vía Telethon.

Reusa el cliente Telethon ya inicializado en SpamReporter para no abrir
una segunda sesión. Devuelve count de fotos, fecha de la más antigua y más
reciente, y una heurística de "probable real / sospechoso / bot" basada en
la edad de la foto más antigua.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class UserSignals:
    user_id: int
    photo_count: int = 0
    oldest_photo: Optional[_dt.datetime] = None
    newest_photo: Optional[_dt.datetime] = None
    bio: Optional[str] = None
    is_premium: bool = False

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
            return "🔴 sin foto (probable bot)"
        age = self.account_age_days or 0
        if age > 365:
            return f"🟢 cuenta con {age}d (probable real)"
        if age > 90:
            return f"🟡 cuenta con {age}d (revisar)"
        return f"🟠 foto reciente ({age}d)"


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
            parts = await client.get_participants(chat_id, search=first_name[:32], limit=15)
            for p in parts:
                if getattr(p, "id", None) == user_id:
                    return p
        except Exception as exc:  # noqa: BLE001
            log.debug("get_participants(search=%r) fallo: %s", first_name, exc)
    # 2) Vía el canal: GetParticipantRequest (funciona si el user ya está cacheado)
    if chat_id is not None:
        try:
            from telethon.tl.functions.channels import GetParticipantRequest
            channel = await client.get_entity(chat_id)
            res = await client(GetParticipantRequest(channel=channel, participant=user_id))
            for u in getattr(res, "users", None) or []:
                if getattr(u, "id", None) == user_id:
                    return u
        except Exception as exc:  # noqa: BLE001
            log.debug("GetParticipant user=%s chat=%s fallo: %s", user_id, chat_id, exc)
    # 3) get_entity directo (funciona si ya está en caché)
    try:
        return await client.get_entity(user_id)
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
    """Obtiene señales de un usuario vía Telethon. Devuelve None si falla.

    `chat_id` + `first_name` permiten resolver la entidad de cuentas recién
    llegadas (no cacheadas) vía get_participants(search=nombre).
    """
    if client is None:
        return None
    try:
        sig = UserSignals(user_id=user_id)
        entity = await _resolve_entity(client, user_id, chat_id, first_name)
        if entity is None:
            return None
        # Fotos: get_profile_photos devuelve Photo[] con .date
        try:
            photos = await client.get_profile_photos(entity, limit=20)
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
            full = await client(GetFullUserRequest(entity))
            sig.bio = (full.full_user.about or "").strip()[:300] or None
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
    parts = [f"\n🔎 <b>Perfil:</b> {sig.verdict}"]
    parts.append(f"📷 fotos: {sig.photo_count}")
    if sig.oldest_photo:
        parts.append(f"foto más antigua: <code>{sig.oldest_photo.strftime('%Y-%m-%d')}</code>")
    if sig.newest_photo and sig.newest_photo != sig.oldest_photo:
        parts.append(f"más reciente: <code>{sig.newest_photo.strftime('%Y-%m-%d')}</code>")
    if sig.is_premium:
        parts.append("⭐ premium")
    if sig.bio:
        import html as _html
        parts.append(f"\n📝 <b>Bio:</b> <i>{_html.escape(sig.bio)}</i>")
    return " · ".join(parts[:4]) + ("\n" + parts[4] if len(parts) > 4 else "")
