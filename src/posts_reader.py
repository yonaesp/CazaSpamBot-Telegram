"""Leer los «Posts» del perfil: las historias que la persona deja fijadas.

Telegram enseña en el perfil una pestaña «Posts» con las historias fijadas, que
no caducan. Es un escaparate más, como la bio o el canal personal, y el que más
cabe: fotos y vídeos con su pie, sin límite de caracteres. La Bot API no lo ve.

Caso que lo motivó (1-nov-2026, Windows 11): «𝐙𝐄𝐑𝐎» (@zerotrace505) entró a las
21:36, pasó la verificación en 6 s, no escribió nada y lo baneó a mano otro admin
dos minutos después. Bio vacía, sin canal, nombre normal: para el bot, limpio.
Sus 15 posts eran un catálogo entero: «Recuperación de estafas de criptomonedas»,
«La recuperación de dinero es segura», «Vincula WhatsApp a tu dispositivo y
espía», «Quieres saber si tu pareja te engaña, comunícate con nosotros». La mitad
del reclamo iba solo dentro de la imagen, por eso se pasa OCR a las fotos.

Lo que se ha comprobado antes de usarlo:

1. **No delata la cuenta.** `stories.getPinnedStories` y la descarga del fichero
   NO cuentan como visualización (las vistas solo suben con
   `stories.incrementStoryViews`/`readStories`, que no se llaman nunca).
2. **Es barato.** Medido con ZERO: la lista de 12 posts en 0,09 s, cada foto en
   0,05-0,23 s (32-153 KB) y el OCR en 0,3-2 s por foto. `GetFullUser`, que ya se
   pide para la bio, dice si hay posts (`stories_pinned_available`): quien no
   tiene no cuesta ni una llamada.
3. **No bloquea al bot.** Con OCR son varios segundos, y PTB procesa los updates
   de uno en uno: esto se llama solo desde trabajos de fondo (el repaso de recién
   llegados y una tarea aparte lanzada en el join), nunca en la ruta del mensaje.
4. **El OCR de cada post se recuerda.** Un post no cambia de imagen, así que se
   guarda su texto por (persona, post): releer el perfil una hora después cuesta
   una llamada y el OCR solo de lo nuevo.

Los vídeos aportan su pie y nada más: su miniatura es de 3-15 KB y el OCR no sacó
nada legible de ninguna de las tres de ZERO.

Best-effort de principio a fin: sin Telethon, sin Tesseract o ante cualquier
error se devuelve lo que se tenga (o None) y el bot sigue como antes.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from . import ocr

log = logging.getLogger("antispam")

# Cuántos posts se leen. Un escaparate de spam repite el mismo reclamo y los
# fijados salen primero; ZERO tenía 15 y con los 10 primeros sobraba.
MAX_POSTS = 10

# Topes. Por llamada, como en `story_reader` y `channel_reader` (ante un FloodWait
# Telethon DUERME sola hasta 60 s sin lanzar excepción), y de la lectura entera,
# que con OCR de diez fotos puede pasar de 10 s en el peor caso.
_TIMEOUT_S = 5.0
_TIMEOUT_TOTAL_S = 60.0

# Tope de texto por post: los detectores trabajan con regex y una captura de
# pantalla de un chat entero no aporta más por ser más larga.
_MAX_CHARS_POST = 800

# Lectura entera por persona. Corta a propósito: los posts se ponen cuando le
# conviene al spammer (como el canal, ver `recien_llegados.RELECTURA_PERFIL_S`).
_TTL_S = 3600
_CACHE_MAX = 500
_cache: dict[int, tuple[float, list | None]] = {}

# Texto de cada foto ya leída, por (persona, post). Sin caducidad: la imagen de
# un post no cambia. Acotado para que no crezca sin fin.
_OCR_MAX = 3000
_ocr_hecho: dict[tuple[int, int], str] = {}


@dataclass(frozen=True)
class Post:
    """Lo legible de un post: su pie y, si es una foto, lo que dice la imagen."""
    id: int
    pie: str = ""
    imagen: str = ""

    @property
    def texto(self) -> str:
        return "\n".join(p for p in (self.pie, self.imagen) if p)


def _de_cache(user_id: int):
    dato = _cache.get(user_id)
    if dato is None:
        return False, None
    puesto, posts = dato
    if time.time() - puesto > _TTL_S:
        del _cache[user_id]
        return False, None
    return True, posts


def _guardar(user_id: int, posts: list | None) -> None:
    if len(_cache) >= _CACHE_MAX:
        viejo = min(_cache, key=lambda k: _cache[k][0])
        del _cache[viejo]
    _cache[user_id] = (time.time(), posts)


def _recordar_ocr(clave: tuple[int, int], texto: str) -> None:
    if len(_ocr_hecho) >= _OCR_MAX:
        # Fuera el primero que entró (los dict conservan el orden de inserción).
        del _ocr_hecho[next(iter(_ocr_hecho))]
    _ocr_hecho[clave] = texto


async def leer(client, entidad, user_id: int) -> list[Post] | None:
    """Los posts fijados del perfil, o None si no se pudieron leer.

    `entidad` es el `User` que ya resolvió `user_signals` (así no se paga otra
    resolución). None significa «no lo sé», nunca «está limpio»; una lista vacía
    sí es «no tiene posts».
    """
    if client is None or entidad is None or not user_id:
        return None
    hay, posts = _de_cache(user_id)
    if hay:
        return posts
    try:
        posts = await asyncio.wait_for(_leer(client, entidad, user_id), _TIMEOUT_TOTAL_S)
    except asyncio.TimeoutError:
        log.info("posts_reader: los posts de %s tardaron demasiado", user_id)
        posts = None
    except Exception as exc:  # noqa: BLE001 — jamás puede tumbar la moderación
        log.info("posts_reader: posts de %s ilegibles: %s", user_id, exc)
        posts = None
    _guardar(user_id, posts)
    return posts


async def _leer(client, entidad, user_id: int) -> list[Post]:
    from telethon.tl.functions.stories import GetPinnedStoriesRequest
    res = await asyncio.wait_for(
        client(GetPinnedStoriesRequest(peer=entidad, offset_id=0, limit=MAX_POSTS)),
        _TIMEOUT_S)
    posts: list[Post] = []
    fotos = 0
    for item in list(getattr(res, "stories", None) or [])[:MAX_POSTS]:
        story_id = getattr(item, "id", None)
        if story_id is None:
            continue
        pie = (getattr(item, "caption", "") or "").strip()
        # Los enlaces de una historia pueden ir como pegatina (`MediaAreaUrl`) y no
        # en el pie: se añaden como texto para que cuenten igual.
        for area in getattr(item, "media_areas", None) or []:
            url = getattr(area, "url", None)
            if url:
                pie = f"{pie}\n{url}".strip()
        imagen = ""
        media = getattr(item, "media", None)
        if type(media).__name__ == "MessageMediaPhoto" and ocr.disponible():
            clave = (user_id, story_id)
            if clave in _ocr_hecho:
                imagen = _ocr_hecho[clave]
            else:
                try:
                    datos = await asyncio.wait_for(
                        client.download_media(media, file=bytes), _TIMEOUT_S)
                    imagen = await ocr.leer(datos) if datos else ""
                    fotos += 1
                    _recordar_ocr(clave, imagen)
                except Exception as exc:  # noqa: BLE001
                    log.debug("posts_reader: foto %s de %s ilegible: %s",
                              story_id, user_id, exc)
        posts.append(Post(id=story_id, pie=pie[:_MAX_CHARS_POST],
                          imagen=imagen[:_MAX_CHARS_POST]))
    log.info("posts_reader: user=%s %d posts leídos de %s fijados, %d fotos nuevas por OCR",
             user_id, len(posts), getattr(res, "count", "?"), fotos)
    return posts
