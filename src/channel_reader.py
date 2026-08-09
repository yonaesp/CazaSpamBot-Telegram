"""Leer lo que PUBLICA el canal enlazado en un perfil, no solo cómo se titula.

`detectors/personal_channel.py` juzgaba el escaparate por el rótulo. Es la mitad
de la evidencia, y la mitad floja: el título lo elige el spammer sabiendo que se
ve, mientras que los posts son donde de verdad dice a qué se dedica.

Caso que lo destapó (2026-08-08, Windows 11): cuenta «Vickycat46», nombre latino
y foto de perfil normal, con un canal titulado `恒泰招聘车队高速结算`. Ese título
sumaba 85 de los 100 puntos necesarios y se quedaba fuera por tener foto. El
primer post del canal era una confesión entera:

    洗米来有码就要 无风险 日3-8k ... 担保公群 https://t.me/+...

Nótese `洗米` («lavar arroz») donde la lista esperaba `洗钱` («lavar dinero»):
jerga deliberada para esquivar filtros de palabras. Contra eso, mirar el título
siempre irá por detrás; mirar lo que publican es mirar la prueba.

Es la misma decisión que ya se tomó en `story_reader` (leer la historia en vez de
adivinar) y en `link_reader` (leer a dónde lleva el enlace): cuando la evidencia
existe y se puede leer, se lee.

Tres cosas confirmadas antes de usarlo:

1. **No delata la cuenta.** Pedir el historial (`messages.getHistory`) NO cuenta
   como visualización: el contador de vistas de un canal solo sube llamando
   aparte a `messages.getMessagesViews` con `increment` (core.telegram.org/api/
   channel). El dueño del canal no puede ver quién lo ha leído.
2. **No se une a nada.** Un canal público se lee sin suscribirse; uno privado da
   error y se devuelve lo que se tenga. Nunca se llama a `JoinChannel`.
3. **Se usa la entidad ya resuelta** que viene en `GetFullUser.chats`, así que no
   hay `contacts.ResolveUsername` de por medio, que es la llamada más propensa a
   FloodWait.

Solo se paga cuando puede cambiar el veredicto: el handler lee el canal ÚNICAMENTE
si el título por sí solo no ha bastado para decidir. En la muestra medida (131
recién llegados de 14 días) apenas 6 tenían canal, así que el coste es residual.
"""
from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger("antispam")

# PTB procesa los updates de UNO EN UNO, así que cada segundo aquí es un segundo
# en el que el bot no modera nada más. Y ante un FloodWait Telethon DUERME sola
# hasta 60 s sin lanzar excepción: sin tope, esto congela el bot. Mismos valores
# que `story_reader`, que ya se topó con ello.
_TIMEOUT_S = 5.0
_TIMEOUT_TOTAL_S = 6.0

# Cuántos posts se leen. Los canales de esta clase repiten el mismo reclamo, así
# que con los últimos sobra; pedir más solo alarga la llamada.
_MAX_POSTS = 5

# Tope del texto devuelto. Los detectores trabajan con regex sobre él y no hace
# falta más para reconocer un reclamo.
_MAX_CHARS = 1200

# Caché por canal. Una red de spam enlaza el MISMO canal desde decenas de cuentas
# (medido: 6 cuentas, 2 canales), así que esto evita repetir la llamada en cada
# entrada. TTL corto porque un canal puede cambiar de contenido.
_TTL_S = 6 * 3600
_CACHE_MAX = 500
_cache: dict[int, tuple[float, str | None]] = {}


def _de_cache(canal_id: int):
    """(hay_dato, texto). Se cachean también los fallos: un canal ilegible lo
    seguirá siendo dentro de un minuto, y reintentar cuesta tiempo del bot."""
    dato = _cache.get(canal_id)
    if dato is None:
        return False, None
    puesto, texto = dato
    if time.time() - puesto > _TTL_S:
        del _cache[canal_id]
        return False, None
    return True, texto


def _guardar(canal_id: int, texto: str | None) -> None:
    if len(_cache) >= _CACHE_MAX:
        # Se va el más viejo. Con TTL de 6 h esto casi nunca entra, pero sin ello
        # el diccionario solo crece.
        viejo = min(_cache, key=lambda k: _cache[k][0])
        del _cache[viejo]
    _cache[canal_id] = (time.time(), texto)


async def leer(client, entidad, canal_id: int) -> str | None:
    """Devuelve la descripción y los últimos posts del canal, o None.

    `entidad` es el objeto `Channel` que ya viene resuelto en `GetFullUser.chats`.
    Best-effort de principio a fin: cualquier fallo devuelve None y el bot sigue
    juzgando por el título, exactamente como antes.
    """
    if client is None or entidad is None or not canal_id:
        return None
    hay, texto = _de_cache(canal_id)
    if hay:
        return texto
    try:
        texto = await asyncio.wait_for(_leer(client, entidad), _TIMEOUT_TOTAL_S)
    except asyncio.TimeoutError:
        log.info("channel_reader: el canal %s tardó demasiado", canal_id)
        texto = None
    except Exception as exc:  # noqa: BLE001 — jamás puede tumbar la moderación
        log.debug("channel_reader: canal %s ilegible: %s", canal_id, exc)
        texto = None
    _guardar(canal_id, texto)
    return texto


async def _leer(client, entidad) -> str | None:
    trozos: list[str] = []

    # 1) La descripción del canal. Va aparte del título y suele ser más explícita.
    try:
        from telethon.tl.functions.channels import GetFullChannelRequest
        full = await asyncio.wait_for(client(GetFullChannelRequest(entidad)), _TIMEOUT_S)
        about = (getattr(full.full_chat, "about", "") or "").strip()
        if about:
            trozos.append(about)
    except Exception as exc:  # noqa: BLE001
        log.debug("channel_reader: sin descripción: %s", exc)

    # 2) Lo que publica, que es la prueba de verdad.
    try:
        posts = await asyncio.wait_for(
            client.get_messages(entidad, limit=_MAX_POSTS), _TIMEOUT_S)
        for m in posts or []:
            # `.message` es el texto plano; un post solo con imagen no aporta nada
            # que un regex pueda leer, y se salta sin más.
            cuerpo = (getattr(m, "message", "") or "").strip()
            if cuerpo:
                trozos.append(cuerpo)
    except Exception as exc:  # noqa: BLE001
        log.debug("channel_reader: sin posts: %s", exc)

    if not trozos:
        return None
    return "\n".join(trozos)[:_MAX_CHARS]
