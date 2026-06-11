"""Lookup en lols.bot — alternativa/complemento a CAS.

Endpoint: GET https://api.lols.bot/account?id=<user_id>
Response: {"ok": true, "user_id": N, "banned": bool, "when": "...", "offenses": N}
(Formato puede variar. Defensivo.)
"""
from __future__ import annotations

import logging

import aiohttp

from . import Hit

log = logging.getLogger(__name__)

_LOLS_URL = "https://api.lols.bot/account"


async def check(user_id: int, session: aiohttp.ClientSession) -> Hit:
    try:
        async with session.get(
            _LOLS_URL,
            params={"id": user_id},
            timeout=aiohttp.ClientTimeout(total=4),
        ) as resp:
            if resp.status != 200:
                return Hit.none()
            data = await resp.json(content_type=None)
    except Exception as exc:
        log.debug("lols.bot lookup user=%s falló: %s", user_id, exc)
        return Hit.none()
    if not isinstance(data, dict):
        return Hit.none()
    # Defensivo ante distintos formatos posibles
    banned = data.get("banned") or data.get("is_banned") or False
    offenses = int(data.get("offenses", 0) or 0)
    if not banned and offenses == 0:
        return Hit.none()
    return Hit(
        rule="lols_match",
        score=100,  # Ban tier: lols.bot es crowdsourced pero con filtrado serio.
        # Si falla, kick no aporta (el user puede seguir viendo el grupo desde fuera).
        # Falsos positivos se corrigen con /unban manual.
        reason=f"lols.bot: usuario marcado (offenses={offenses})",
        payload={"banned": banned, "offenses": offenses},
    )
