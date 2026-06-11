"""Detector: fotos de perfil subidas en ráfaga corta = cuenta construida.

Un usuario humano normal sube sus fotos de perfil ESPACIADAS en el tiempo
(días, semanas, meses entre actualizaciones). Una cuenta fake construida
para suplantar identidad sube todas las fotos seguidas en segundos/minutos.

Caso real (Javier Zamora, 2026-05-26): 5 fotos del mismo individuo subidas
en 18 segundos. Robo de identidad típico de spammers.

Requiere Telethon (reporter.get_client()). Sin Telethon, el detector no
dispara (devuelve Hit.none()).
"""
from __future__ import annotations

import logging
from typing import Optional

from . import Hit

log = logging.getLogger(__name__)

# Si N fotos están dentro de una ventana de SPAN_SECONDS, se considera batch.
MIN_PHOTOS = 3        # mínimo de fotos a evaluar
SPAN_SECONDS = 120    # ventana máxima (2 min) — todas subidas en <2 min = batch claro


async def check(
    client, user_id: int, username: Optional[str] = None,
    min_photos: int = MIN_PHOTOS, span_seconds: int = SPAN_SECONDS,
) -> Hit:
    """Devuelve Hit con score alto si las últimas fotos están en batch corto.

    Estrategia de resolución:
      1. get_entity(user_id) — funciona si Telethon ya lo conoce.
      2. get_entity("@" + username) — fallback si tenemos username.
      3. Si nada resuelve, no dispara (Hit.none()).
    """
    if client is None:
        return Hit.none()

    entity = None
    try:
        entity = await client.get_entity(user_id)
    except Exception:
        if username:
            try:
                entity = await client.get_entity(f"@{username.lstrip('@')}")
            except Exception as exc:
                log.debug("photos_batch get_entity(@%s) fallo: %s", username, exc)
        else:
            log.debug("photos_batch get_entity(%s) sin username", user_id)

    if entity is None:
        return Hit.none()

    try:
        photos = await client.get_profile_photos(entity, limit=5)
    except Exception as exc:
        log.debug("photos_batch get_profile_photos user=%s fallo: %s", user_id, exc)
        return Hit.none()

    if not photos or len(photos) < min_photos:
        return Hit.none()

    timestamps = [p.date.timestamp() for p in photos]
    span = max(timestamps) - min(timestamps)
    if span > span_seconds:
        return Hit.none()

    # BYPASS anti-FP: si la foto más ANTIGUA tiene >365 días, la cuenta no es
    # recién creada. Un spammer con identidad robada sube todo el batch al
    # crear la cuenta (fotos recientes); una cuenta vieja con fotos viejas en
    # batch puede ser un user real que subió su galería de golpe hace años.
    import time as _t
    oldest_age_days = (_t.time() - min(timestamps)) / 86400
    if oldest_age_days >= 365:
        log.info(
            "photos_batch BYPASS user=%s: fotos en batch pero cuenta >1 año (%dd)",
            user_id, int(oldest_age_days),
        )
        return Hit.none()

    return Hit(
        rule="photos_batch_upload",
        score=100,
        reason=(
            f"{len(photos)} fotos de perfil subidas en {span:.0f}s "
            f"(humanos normales distribuyen fotos en días/meses, no segundos)"
        ),
        payload={
            "n_photos": len(photos),
            "span_seconds": round(span, 1),
            "first_ts": min(timestamps),
            "last_ts": max(timestamps),
        },
    )
