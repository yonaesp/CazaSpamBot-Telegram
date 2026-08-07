"""Leer QUÉ HAY al otro lado de un enlace `t.me` antes de juzgarlo.

Hasta ahora un enlace a otro chat de Telegram era una señal a ciegas: el bot veía
«hay un t.me a un chat externo» y puntuaba por el hecho de que existiera, sin saber
si llevaba a un canal de domótica o a uno de packs. Con esa incertidumbre no queda
más remedio que ser blando, y ahí se coló el caso real que originó esto:

    24/07/2026, grupo de domótica. Una cuenta con dos años y 34 mensajes publica
    `https://t.me/EromeVideosPacks`. El bot lo detectó (`external_mention_or_link`,
    50 puntos), pero como el autor era veterano aplicó el aviso suave: recordatorio
    de normas que se autoborra y el enlace INTACTO en el grupo. Una hora después,
    otro miembro escribía «este se le ha escapado al bot».

El destino, sin embargo, se presenta solo: ese canal se titula «Mujeres / Packs /
Caseros / ... / Jovencitas / Colegialas» y se describe como «Mejor grupo de packs y
videos exclusivos». Eso ya no es una señal débil, es la prueba. Mismo principio que
`story_reader` (leer la historia en vez de adivinar) y que `personal_channel` (leer
el título del canal del perfil): **se juzga la evidencia real, no el indicio**.

Detalles que conviene no perder de vista al tocar esto:

- **Enlaces privados incluidos.** `t.me/+HASH` y `t.me/joinchat/HASH` no se pueden
  resolver como usuario, pero `messages.checkChatInvite` devuelve título y
  descripción SIN entrar al chat. Es justo el formato que más usa el spam.
- **No se entra a ningún sitio.** Ni join, ni lectura de mensajes: solo la ficha
  pública. La cuenta secundaria no aparece como miembro ni deja rastro.
- **El tiempo es el enemigo.** PTB procesa los updates de uno en uno, así que cada
  espera aquí congela el bot entero. De ahí el tope por llamada, el tope total y
  el máximo de enlaces por mensaje.
- **Se cachea el resultado, también el negativo.** Resolver un @username dispara
  `contacts.ResolveUsername`, de lo más propenso a FloodWait. Un canal de spam se
  publica muchas veces seguidas: la primera se paga, las demás salen gratis.
- Es best-effort de principio a fin: sin Telethon, con error o con timeout se
  devuelve None y el bot se comporta exactamente como antes.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

log = logging.getLogger("antispam")

# Mismos topes que `story_reader`, y por el mismo motivo: con los updates en serie,
# lo peor que puede pasar son 6 s de bot congelado, no 10 ni 60.
_TIMEOUT_S = 5.0
_TIMEOUT_TOTAL_S = 6.0

# Cuántos enlaces de un mismo mensaje se miran. Un mensaje con veinte t.me no
# necesita veinte resoluciones para saber que es spam: con los primeros basta.
_MAX_ENLACES = 2

_TTL_S = 6 * 3600
_CACHE_MAX = 500
_cache: dict[str, tuple[float, "Destino | None"]] = {}

_HOSTS = {"t.me", "telegram.me", "telegram.dog"}

# Primeros segmentos de t.me que NO son el nombre de un chat. Resolverlos como
# @username no daría un canal, daría un error o (peor) una cuenta cualquiera que
# se llame igual que la palabra reservada.
_RESERVADOS = {
    "joinchat", "addstickers", "addemoji", "addtheme", "addlist", "share", "proxy",
    "socks", "login", "iv", "setlanguage", "confirmphone", "bg", "contact",
    "invoice", "giftcode", "boost", "m", "s", "c", "k", "a", "blog", "faq",
}

_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


@dataclass(frozen=True)
class Destino:
    """Lo que se puede ver de un chat de Telegram sin entrar en él."""

    titulo: str
    descripcion: str
    url: str
    chat_id: int | None = None

    @property
    def texto(self) -> str:
        """Título y descripción juntos: es lo que se pasa al detector."""
        return "\n".join(p for p in (self.titulo, self.descripcion) if p)


def limpiar_cache() -> None:
    """Olvida los destinos cacheados (tests)."""
    _cache.clear()


def _clave(url: str) -> str | None:
    """Identificador del destino dentro de la URL, o None si no es un t.me útil."""
    if "://" not in url:
        url = "https://" + url
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host not in _HOSTS:
        return None
    partes = [p for p in parsed.path.split("/") if p]
    if not partes:
        return None
    primero = partes[0]
    if primero.startswith("+"):
        return "invite:" + primero[1:]
    if primero.lower() == "joinchat" and len(partes) > 1:
        return "invite:" + partes[1]
    if primero.lower() in _RESERVADOS:
        return None
    if not _USERNAME_RE.match(primero):
        return None
    return "user:" + primero.lower()


async def leer(context, urls, *, es_moderado=None) -> Destino | None:
    """Ficha pública del primer destino legible, o None.

    `es_moderado(chat_id)` permite descartar los enlaces a nuestros propios grupos:
    ahí el destino ya lo conocemos y no hay nada que juzgar.
    """
    try:
        return await asyncio.wait_for(_leer(context, urls, es_moderado), _TIMEOUT_TOTAL_S)
    except asyncio.TimeoutError:
        log.info("link_reader: se agotó el tiempo total leyendo el destino de %s", urls[:1])
        return None
    except Exception as exc:  # noqa: BLE001 - nunca debe romper la moderación
        log.info("link_reader: fallo inesperado (%s); se sigue sin destino", exc)
        return None


async def _leer(context, urls, es_moderado) -> Destino | None:
    claves: list[tuple[str, str]] = []
    vistas: set[str] = set()
    for url in urls or []:
        clave = _clave(url)
        if clave and clave not in vistas:
            vistas.add(clave)
            claves.append((clave, url))
        if len(claves) >= _MAX_ENLACES:
            break
    if not claves:
        return None

    # Lo cacheado se resuelve antes de mirar siquiera si hay Telethon: si el destino
    # ya se leyó una vez, esta llamada no cuesta nada.
    pendientes: list[tuple[str, str]] = []
    for clave, url in claves:
        guardado = _cache.get(clave)
        if guardado is not None and (time.time() - guardado[0]) < _TTL_S:
            if guardado[1] is not None:
                return guardado[1]
            continue
        pendientes.append((clave, url))
    if not pendientes:
        return None

    reporter = context.bot_data.get("reporter")
    client = reporter.get_client() if reporter else None
    if client is None:
        return None                      # sin Telethon el bot sigue igual que antes

    for clave, url in pendientes:
        destino = await _resolver(client, clave, url)
        _guardar(clave, destino)
        if destino is None:
            continue
        if es_moderado is not None and destino.chat_id is not None:
            try:
                if es_moderado(destino.chat_id):
                    continue             # enlace a uno de nuestros grupos
            except Exception:  # noqa: BLE001
                pass
        return destino
    return None


def _guardar(clave: str, destino: "Destino | None") -> None:
    if len(_cache) >= _CACHE_MAX:
        # Se tira la mitad más vieja de golpe: barato y suficiente para una caché
        # que solo crece con canales distintos enlazados en los grupos.
        for viejo in sorted(_cache, key=lambda k: _cache[k][0])[: _CACHE_MAX // 2]:
            _cache.pop(viejo, None)
    _cache[clave] = (time.time(), destino)


async def _resolver(client, clave: str, url: str) -> Destino | None:
    tipo, valor = clave.split(":", 1)
    if tipo == "invite":
        return await _por_invitacion(client, valor, url)
    return await _por_username(client, valor, url)


async def _por_invitacion(client, hash_: str, url: str) -> Destino | None:
    """Título y descripción de un chat privado, SIN entrar en él."""
    try:
        from telethon.tl.functions.messages import CheckChatInviteRequest
    except Exception:  # noqa: BLE001 - Telethon es opcional
        return None
    try:
        res = await asyncio.wait_for(client(CheckChatInviteRequest(hash_)), _TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - INVITE_HASH_EXPIRED, FloodWait...
        log.debug("link_reader: invitación %s ilegible: %s", hash_[:8], exc)
        return None
    # ChatInvite (aún no dentro) trae title/about sueltos; ChatInviteAlready y
    # ChatInvitePeek envuelven el chat de verdad.
    chat = getattr(res, "chat", None)
    titulo = getattr(res, "title", None) or getattr(chat, "title", None) or ""
    about = getattr(res, "about", None) or ""
    if not titulo and not about:
        return None
    return Destino(titulo=titulo[:300], descripcion=str(about)[:600], url=url,
                   chat_id=getattr(chat, "id", None))


async def _por_username(client, username: str, url: str) -> Destino | None:
    try:
        entidad = await asyncio.wait_for(client.get_entity(username), _TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - USERNAME_NOT_OCCUPIED, FloodWait...
        log.debug("link_reader: @%s irresoluble: %s", username, exc)
        return None

    titulo = (getattr(entidad, "title", None)
              or " ".join(p for p in (getattr(entidad, "first_name", None),
                                      getattr(entidad, "last_name", None)) if p))
    about = ""
    try:
        from telethon.tl.functions.channels import GetFullChannelRequest
        from telethon.tl.functions.users import GetFullUserRequest
        if getattr(entidad, "broadcast", None) is not None or getattr(entidad, "megagroup", None) is not None:
            full = await asyncio.wait_for(client(GetFullChannelRequest(entidad)), _TIMEOUT_S)
            about = getattr(full.full_chat, "about", "") or ""
        elif getattr(entidad, "bot", None) is not None or getattr(entidad, "first_name", None):
            full = await asyncio.wait_for(client(GetFullUserRequest(entidad)), _TIMEOUT_S)
            about = getattr(full.full_user, "about", "") or ""
    except Exception as exc:  # noqa: BLE001 - la descripción es un extra, no un requisito
        log.debug("link_reader: sin descripción de @%s: %s", username, exc)

    if not titulo and not about:
        return None
    return Destino(titulo=str(titulo)[:300], descripcion=str(about)[:600], url=url,
                   chat_id=getattr(entidad, "id", None))
