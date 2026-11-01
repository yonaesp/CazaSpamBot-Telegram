"""Versiones nuevas: avisar al admin de cada copia y contarle cómo fue la actualización (L51).

El admin (1-nov-2026) quiere que el bot lo use cuanta más gente mejor y que actualizar
sea fácil. Una vez al día se pregunta a GitHub cuál es la última versión publicada (una
consulta anónima a api.github.com, sin nada del bot ni de los grupos) y, si es más nueva
que la que corre, se avisa por privado, en silencio y una sola vez por versión. Se apaga
con UPDATE_CHECK=false.

Instalar no lo hace el bot: no puede (ni debe) tocar su propio contenedor. Lo hace
`update.sh` en el servidor, a mano o cada noche con `./update.sh --auto`. Antes de
reiniciar deja `data/update-pending.json` con la versión de origen y la de destino; el
bot que arranca después lo lee y cuenta si se quedó la nueva o se volvió a la anterior.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from pathlib import Path

import aiohttp
from telegram.error import TelegramError

from . import notify_prefs, publico
from .i18n import t
from .version import __version__

log = logging.getLogger("antispam.actualizaciones")

PREF_AVISADA = "_version_avisada"
PENDIENTE = Path("/app/data/update-pending.json")
# Un pendiente más viejo es de una actualización que no llegó a reiniciar el bot.
PENDIENTE_MAX_S = 6 * 3600
_TIMEOUT = aiohttp.ClientTimeout(total=15)
_REPO_RE = re.compile(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def activado() -> bool:
    return os.environ.get("UPDATE_CHECK", "true").strip().lower() not in (
        "false", "0", "no", "off")


def version_tupla(texto: str | None) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (texto or "").strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def api_ultima(repo_url: str | None = None) -> str:
    """API de la última versión del repo de REPO_URL; si no es de GitHub, la del original."""
    url = publico.repo_url() if repo_url is None else repo_url
    m = _REPO_RE.search(url or "") or _REPO_RE.search(publico.REPO_URL_DEFECTO)
    return f"https://api.github.com/repos/{m[1]}/{m[2]}/releases/latest"


async def ultima_version(session: aiohttp.ClientSession, url: str) -> dict | None:
    """`{tag, url}` de la última versión publicada, o None si no hay ninguna o no se pudo saber."""
    cabeceras = {"Accept": "application/vnd.github+json",
                 "User-Agent": f"CazaSpamBot/{__version__}"}
    try:
        async with session.get(url, headers=cabeceras, timeout=_TIMEOUT) as r:
            if r.status == 404:  # el repo aún no ha publicado ninguna
                return None
            if r.status != 200:
                log.warning("actualizaciones: GitHub respondió %s", r.status)
                return None
            datos = await r.json()
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        log.warning("actualizaciones: no se pudo consultar GitHub: %s", exc)
        return None
    tag = datos.get("tag_name") if isinstance(datos, dict) else None
    if not version_tupla(tag) or datos.get("draft") or datos.get("prerelease"):
        return None
    return {"tag": tag, "url": datos.get("html_url") or ""}


async def comprobar_job(context) -> None:
    """Una vez al día: si hay una versión más nueva, se avisa al admin (una vez por versión)."""
    if not activado():
        return
    cfg, db = context.bot_data["cfg"], context.bot_data["db"]
    session = context.bot_data.get("http")
    actual = version_tupla(__version__)
    if session is None or not cfg.admin_notify_chat_id or not actual:
        return
    ultima = await ultima_version(session, api_ultima())
    if not ultima or version_tupla(ultima["tag"]) <= actual:
        return
    if db.get_text_pref(PREF_AVISADA) == ultima["tag"]:
        return
    texto = t("act.nueva", nueva=html.escape(ultima["tag"]), actual=f"v{__version__}",
              url=html.escape(ultima["url"], quote=True))
    # Una versión mayor puede pedir cambios a mano: la noche no la instala sola.
    mayor = version_tupla(ultima["tag"])[0] > actual[0]
    texto += "\n\n" + t("act.mayor" if mayor else "act.auto")
    try:
        await context.bot.send_message(
            chat_id=cfg.admin_notify_chat_id, text=texto, parse_mode="HTML",
            disable_web_page_preview=True,
            disable_notification=notify_prefs.sin_sonido(db, importante=False),
        )
    except TelegramError as exc:
        log.warning("actualizaciones: no se pudo avisar de %s: %s", ultima["tag"], exc)
        return
    db.set_text_pref(PREF_AVISADA, ultima["tag"])
    log.info("actualizaciones: avisado de %s (corre v%s)", ultima["tag"], __version__)


def leer_pendiente(ruta: Path | None = None) -> dict | None:
    """Lee y borra lo que dejó `update.sh` antes de reiniciar. None si no hay nada que contar."""
    ruta = ruta or PENDIENTE
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("actualizaciones: %s ilegible (%s); se descarta", ruta.name, exc)
        datos = None
    try:
        ruta.unlink()
    except OSError as exc:
        # Sin poder borrarlo se contaría en cada reinicio: mejor no contarlo.
        log.warning("actualizaciones: no se pudo borrar %s: %s", ruta.name, exc)
        return None
    if not isinstance(datos, dict) or time.time() - float(datos.get("ts") or 0) > PENDIENTE_MAX_S:
        return None
    if not version_tupla(datos.get("to")):
        return None
    return datos


async def informar_job(context) -> None:
    """Al minuto de arrancar: cuenta cómo fue la actualización que acaba de hacer `update.sh`."""
    datos = leer_pendiente()
    cfg, db = context.bot_data["cfg"], context.bot_data["db"]
    if not datos or not cfg.admin_notify_chat_id:
        return
    nueva, antes = datos["to"], datos.get("from") or "?"
    if version_tupla(nueva) == version_tupla(__version__):
        texto = t("act.hecha", nueva=html.escape(nueva), antes=html.escape(antes))
    else:
        # Arranca otra versión: la nueva no se sostuvo y `update.sh` volvió atrás.
        # Sigue protegiendo con la anterior, así que no hace falta que suene.
        texto = t("act.fallida", nueva=html.escape(nueva), actual=f"v{__version__}")
    log.info("actualizaciones: %s → %s, corre v%s", antes, nueva, __version__)
    try:
        await context.bot.send_message(
            chat_id=cfg.admin_notify_chat_id, text=texto, parse_mode="HTML",
            disable_web_page_preview=True,
            disable_notification=notify_prefs.sin_sonido(db, importante=False),
        )
    except TelegramError as exc:
        log.warning("actualizaciones: no se pudo contar la actualización: %s", exc)
