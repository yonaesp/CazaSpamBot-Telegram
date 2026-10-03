"""Lo que ve quien NO es de la casa: el perfil del bot y los privados de desconocidos.

Gente ajena encontraba el bot y lo metía en sus grupos (dos de pesca el
25-sep-2026), donde no puede moderar: solo actúa donde es admin y para la
federación de su dueño. Antes de eso, a quien le escribía por privado se le
ignoraba en silencio, así que nadie sabía que el bot es de código abierto y se
puede montar gratis. Aquí se les cuenta, una sola vez y sin insistir.

`REPO_URL` vacío lo apaga todo: quien monte su copia y no quiera anunciar nada
no tiene que tocar código.
"""
from __future__ import annotations

import logging
import os
import time

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from .i18n import SUPPORTED, current_lang, t

log = logging.getLogger(__name__)

REPO_URL_DEFECTO = "https://github.com/yonaesp/CazaSpamBot-Telegram"

# Un desconocido que escribe veinte mensajes no recibe veinte respuestas: el bot
# no puede convertirse en un frontón que cualquiera use para generar tráfico.
_CADA_S = 24 * 3600
_CLAVE = "_publico_respondido"

# Topes de la Bot API: pasarse hace fallar la llamada entera.
_MAX_DESC = 512
_MAX_CORTA = 120


def repo_url() -> str:
    return os.environ.get("REPO_URL", REPO_URL_DEFECTO).strip()


async def responder_privado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Contesta a un desconocido por privado. Devuelve True si contestó."""
    url = repo_url()
    msg, user = update.effective_message, update.effective_user
    if not url or not msg or not user or msg.chat.type != ChatType.PRIVATE:
        return False
    cache = context.bot_data.setdefault(_CLAVE, {})
    ahora = time.time()
    if ahora - cache.get(user.id, 0.0) < _CADA_S:
        return False
    cache[user.id] = ahora
    for uid, visto in list(cache.items()):
        if ahora - visto > _CADA_S:
            del cache[uid]
    await msg.reply_text(t("publico.dm", url=url), parse_mode="HTML",
                         disable_web_page_preview=False)
    log.info("privado de un desconocido user=%s: se le cuenta cómo montarse el bot", user.id)
    return True


async def poner_descripcion(bot) -> None:
    """Descripción del perfil del bot en cada idioma disponible.

    Nunca tumba el arranque: si Telegram la rechaza, se queda la que hubiera.
    """
    url = repo_url()
    if not url:
        return
    # `None` es la que ve quien tiene Telegram en un idioma sin traducción: va
    # en el idioma activo del bot.
    for lang in [None, *sorted(SUPPORTED)]:
        desc = t("publico.descripcion", _lang=lang or current_lang(), url=url)[:_MAX_DESC]
        corta = t("publico.descripcion_corta", _lang=lang or current_lang(), url=url)[:_MAX_CORTA]
        try:
            actual = await bot.get_my_description(language_code=lang)
            if actual.description != desc:
                await bot.set_my_description(desc, language_code=lang)
            actual_c = await bot.get_my_short_description(language_code=lang)
            if actual_c.short_description != corta:
                await bot.set_my_short_description(corta, language_code=lang)
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo poner la descripción (%s): %s", lang, exc)
