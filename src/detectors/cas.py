"""CAS (Combot Anti-Spam) lookup. Cachea en DB para minimizar llamadas."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from . import Hit

log = logging.getLogger(__name__)

_CAS_URL = "https://api.cas.chat/check"


async def check(
    user_id: int,
    session: aiohttp.ClientSession,
    db,
    ttl: int,
) -> Hit:
    cached = db.cas_lookup(user_id, ttl)
    if cached is not None:
        if cached > 0:
            return Hit(
                rule="cas_match",
                score=100,
                reason=f"CAS: usuario baneado globalmente (offenses={cached})",
                payload={"offenses": cached, "cached": True},
            )
        return Hit.none()
    try:
        async with session.get(_CAS_URL, params={"user_id": user_id}, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            data: dict[str, Any] = await resp.json(content_type=None)
    except Exception as exc:
        log.warning("CAS lookup falló para user_id=%s: %s", user_id, exc)
        return Hit.none()
    offenses = 0
    if data.get("ok"):
        offenses = int(data.get("result", {}).get("offenses", 0))
    db.cas_store(user_id, offenses)
    if offenses > 0:
        return Hit(
            rule="cas_match",
            score=100,
            reason=f"CAS: usuario baneado globalmente (offenses={offenses})",
            payload={"offenses": offenses, "cached": False},
        )
    return Hit.none()
