"""CAS (Combot Anti-Spam) lookup. Cachea en DB para minimizar llamadas.

Desde noviembre de 2026 la API pide una clave en cada consulta (`CAS_API_KEY`, la misma
de la API de Combot). Sin ella responde 401 con `ok: false`, y eso no es «no está en la
lista»: un rechazo no se guarda en la caché ni se da por limpio (L65). Solo se da por
limpio lo que CAS dice que no tiene («Record not found»).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import aiohttp

from ..i18n import t
from . import Hit

log = logging.getLogger(__name__)

_CAS_URL = "https://api.cas.chat/check"
ENV_CLAVE = "CAS_API_KEY"
_TIMEOUT = aiohttp.ClientTimeout(total=5)
# Lo que CAS contesta cuando rechaza la clave (o no la lleva).
_CODIGOS_DE_CLAVE = (401, 403)
# Un rechazo o una respuesta rara se apunta en el log como mucho una vez cada tanto:
# con la lista caída, cada entrada al grupo repetiría la misma línea.
_LOG_CADA_S = 1800
_ultimo_log: dict[str, float] = {}
# Lo que lee `cas_vigia`: cuántas consultas ha rechazado CAS desde el arranque y por qué.
estado: dict[str, Any] = {"rechazos": 0, "motivo": ""}

OK = "ok"                        # CAS contestó: `offenses` vale (0 = no está)
RECHAZADA = "rechazada"          # falta la clave o no vale
SIN_RESPUESTA = "sin_respuesta"  # red, o una respuesta que no se entiende


def clave() -> str:
    return (os.environ.get(ENV_CLAVE) or "").strip()


def _avisar_log(tipo: str, texto: str, *args) -> None:
    ahora = time.monotonic()
    if ahora - _ultimo_log.get(tipo, -_LOG_CADA_S) < _LOG_CADA_S:
        return
    _ultimo_log[tipo] = ahora
    log.warning(texto, *args)


async def consultar(user_id: int, session: aiohttp.ClientSession) -> tuple[str, int, str]:
    """Una consulta a CAS, sin caché: `(OK | RECHAZADA | SIN_RESPUESTA, offenses, motivo)`.

    La clave va en la cabecera, nunca en la URL: una URL acaba en los logs.
    """
    k = clave()
    if not k:
        return RECHAZADA, 0, "falta CAS_API_KEY"
    try:
        async with session.get(_CAS_URL, params={"user_id": user_id},
                               headers={"Authorization": f"Bearer {k}"},
                               timeout=_TIMEOUT) as resp:
            status = resp.status
            data = await resp.json(content_type=None)
    except Exception as exc:  # noqa: BLE001 - red, tiempo agotado o JSON roto
        return SIN_RESPUESTA, 0, str(exc).replace(k, "***")[:200]
    if not isinstance(data, dict):
        return SIN_RESPUESTA, 0, f"respuesta ilegible (HTTP {status})"
    if data.get("ok"):
        resultado = data.get("result")
        try:
            return OK, int((resultado if isinstance(resultado, dict) else {}).get("offenses", 0) or 0), ""
        except (TypeError, ValueError):
            return SIN_RESPUESTA, 0, "offenses ilegible"
    motivo = str(data.get("description") or "")[:200]
    codigo = data.get("error_code")
    if status in _CODIGOS_DE_CLAVE or codigo in _CODIGOS_DE_CLAVE:
        return RECHAZADA, 0, motivo or f"HTTP {status}"
    # Así dice CAS que alguien no está en la lista: es la única negativa que cuenta como limpio.
    if "not found" in motivo.lower():
        return OK, 0, ""
    return SIN_RESPUESTA, 0, motivo or f"HTTP {status}"


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
                reason=t("reason.cas_banned", offenses=cached),
                payload={"offenses": cached, "cached": True},
            )
        return Hit.none()
    if not clave():  # sin clave no hay consulta que hacer; lo dice `cas_vigia` al arrancar
        return Hit.none()
    resultado, offenses, motivo = await consultar(user_id, session)
    if resultado == RECHAZADA:
        estado["rechazos"] += 1
        estado["motivo"] = motivo
        _avisar_log(RECHAZADA, "CAS rechaza la consulta (%s): no se sabe nada de user_id=%s", motivo, user_id)
        return Hit.none()
    if resultado == SIN_RESPUESTA:
        _avisar_log(SIN_RESPUESTA, "CAS lookup falló para user_id=%s: %s", user_id, motivo)
        return Hit.none()
    db.cas_store(user_id, offenses)
    if offenses > 0:
        return Hit(
            rule="cas_match",
            score=100,
            reason=t("reason.cas_banned", offenses=offenses),
            payload={"offenses": offenses, "cached": False},
        )
    return Hit.none()
