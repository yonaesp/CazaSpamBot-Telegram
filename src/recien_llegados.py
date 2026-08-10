"""Vigilar al recién llegado que aún no ha escrito.

El bot mira dos veces a cada usuario: **al entrar** y **al escribir su primer
mensaje**. Entre esas dos hay un hueco que puede durar horas o días, y ahí es
donde se cuelan dos cosas medidas en producción, las dos en el grupo de domótica:

1. **lols.bot ficha tarde.** Esas listas se alimentan de denuncias, así que un
   spammer recién creado todavía no está en ellas cuando entra. Medido:

       @Juan  (8681588748)  entró 07/08 07:14 → limpio en lols
                            escribió 08:49    → lols YA lo tenía  (1 h 35 min)
       (8953604344)         entró 06/08 00:01 → limpio en lols
                            escribió 12:16    → lols YA lo tenía  (12 h 14 min)
       (8633122166)         entró 05/08 07:51 → escribió 27 h después, fichado

   El bot no «esperaba a que escribieran»: preguntó al entrar y le dijeron que
   estaban limpios. Solo se enteró al volver a preguntar con el primer mensaje.

2. **El nombre se cambia DESPUÉS de verificarse.** El 8953604344 pasó la
   verificación de botón **en 3 segundos** y doce horas más tarde escribía con el
   nombre `唔活诗我` y el usuario `zBuepQqZEcvifAeaGK`. Con ese nombre, entrar le
   habría costado un ban inmediato (`_is_obvious_spam_profile` lo confirma), así
   que lo lógico es que entrara con otro y se lo cambiara ya dentro. El perfil no
   se volvía a mirar nunca.

Este trabajo cierra el hueco: cada cuarto de hora repasa a los que entraron hace
poco y **todavía no han escrito**, y les vuelve a aplicar exactamente los mismos
criterios del join. Nada nuevo que ajustar, ningún umbral propio: si algo cambió
(la lista ya lo tiene, el nombre ya no es el de antes), se actúa igual que si
acabara de entrar.

Topes, porque esto corre solo y contra APIs de terceros:
- solo se vigila las primeras `VENTANA_S` horas desde la entrada,
- a la misma persona no se le consulta más de una vez por `RECHEQUEO_S`,
- como mucho `MAX_POR_CICLO` personas por vuelta.
"""
from __future__ import annotations

import logging
import time

from telegram.error import TelegramError

from .config import Config
from .db import DB
from .detectors import cas as cas_det
from .detectors import lols_bot as lols_det
from .i18n import t
from .scoring import decide

log = logging.getLogger(__name__)

# Cuánto tiempo se vigila a alguien que acaba de entrar. Un día cubre de sobra los
# casos medidos (el peor tardó 27 h en escribir, pero ya estaba fichado a las 24).
VENTANA_S = 24 * 3600
# Espera mínima entre dos consultas sobre la misma persona.
RECHEQUEO_S = 3600
# Consultas a listas externas (CAS, lols) por vuelta. Con el trabajo cada 15 min
# son 100 a la hora como techo.
MAX_POR_CICLO = 25

# Nombres leídos por vuelta. Muy por encima del anterior porque esto es Bot API:
# gratis, sin límite práctico y sin tocar la cuenta secundaria. El tope existe
# solo para que una avalancha de entradas no convierta una vuelta en cien
# llamadas seguidas.
MAX_NOMBRES_POR_CICLO = 100

# Perfiles que se leen por Telethon en cada vuelta. Acotado porque leer un perfil
# son varias llamadas MTProto con la cuenta secundaria, y quemar su reputación es
# un mal negocio (regla 9 del proyecto). Con 12 por vuelta y el trabajo cada 15
# min salen 48 lecturas a la hora, que cubren de sobra las 16-23 personas que hay
# de media en la ventana.
MAX_PERFILES_POR_CICLO = 12

# Cada cuánto se vuelve a leer el perfil COMPLETO de la misma persona.
#
# Estuvo en 6 horas, con el razonamiento de que «un canal personal no aparece y
# desaparece». Es falso: aparece cuando al spammer le conviene. Caso medido
# (10-ago-2026, Windows 10): «Simongirl40», nombre latino y foto normal, entró a
# las 09:49 y escribió a las 15:32 con el canal `财天下飞机进群结演员结算频道` en
# el perfil, que puntúa 160 de los 100 necesarios. En cualquier momento de esas
# casi seis horas se le habría cazado; el hueco no era del detector, era de esta
# constante.
#
# Con una hora y 16-23 candidatos hacen falta 4-6 lecturas por vuelta: entra
# holgado en el presupuesto de arriba. Si la ventana creciera mucho, el
# presupuesto la degrada sola y algunos esperan un poco más.
RELECTURA_PERFIL_S = 3600

_CLAVE_CACHE = "_recien_llegados_visto"
_CLAVE_PERFILES = "_recien_llegados_perfil"
_CLAVE_PRESUPUESTO = "_recien_llegados_presupuesto"


def _toca_mirar(context, chat_id: int, user_id: int) -> bool:
    """¿Ha pasado ya el tiempo mínimo desde la última consulta sobre esta persona?

    En memoria a propósito: perderlo al reiniciar solo cuesta unas consultas de
    más, y no merece una columna nueva en la base de datos.
    """
    cache = context.bot_data.setdefault(_CLAVE_CACHE, {})
    ahora = time.time()
    if ahora - cache.get((chat_id, user_id), 0.0) < RECHEQUEO_S:
        return False
    cache[(chat_id, user_id)] = ahora
    # La ventana es de un día, así que nada anterior a eso vuelve a hacer falta.
    for clave, visto in list(cache.items()):
        if ahora - visto > VENTANA_S:
            del cache[clave]
    return True


async def revisar_job(context) -> None:
    """Repasa a los recién llegados que aún no han escrito."""
    db: DB = context.bot_data["db"]
    cfg: Config = context.bot_data["cfg"]
    session = context.bot_data.get("http")

    try:
        candidatos = db.recien_llegados_callados(time.time() - VENTANA_S, limite=200)
    except Exception as exc:  # noqa: BLE001 — un trabajo de fondo nunca tumba el bot
        log.warning("recien_llegados: no se pudo consultar la lista: %s", exc)
        return

    mirados = 0
    nombres = 0
    saltados = 0
    # Presupuesto de lecturas de perfil, que se renueva en cada vuelta.
    context.bot_data[_CLAVE_PRESUPUESTO] = MAX_PERFILES_POR_CICLO
    for fila in candidatos:
        chat_id, user_id = fila["chat_id"], fila["user_id"]
        if db.is_banned(user_id) or db.is_whitelisted(chat_id, user_id):
            continue
        espera = int(time.time() - float(fila["join_ts"]))

        # 1) EL NOMBRE, en cada vuelta. `get_chat_member` es Bot API: gratis, sin
        # límite práctico y sin tocar la cuenta secundaria. Es además lo que más
        # cambia, porque el truco consiste justo en entrar con un nombre que pasa
        # los filtros y ponerse el de verdad poco antes de hablar. Tenía la misma
        # espera de una hora que las listas externas, que son APIs de terceros, y
        # eso era regalarle esa hora a cambio de nada: la llamada no cuesta.
        if nombres < MAX_NOMBRES_POR_CICLO:
            nombres += 1
            try:
                if await _revisar_perfil(context, db, cfg, fila, espera):
                    continue
            except Exception as exc:  # noqa: BLE001
                log.warning("recien_llegados: fallo con el perfil de %s: %s", user_id, exc)

        # 2) Las listas externas, que sí son APIs de terceros y conviene espaciar.
        if mirados >= MAX_POR_CICLO:
            continue
        if not _toca_mirar(context, chat_id, user_id):
            saltados += 1
            continue
        mirados += 1
        try:
            if await _revisar_listas(context, db, cfg, session, fila, espera):
                continue
        except Exception as exc:  # noqa: BLE001
            log.warning("recien_llegados: fallo revisando user=%s: %s", user_id, exc)

    # Latido. Sin esto el trabajo era invisible: solo escribía cuando actuaba, así
    # que «no hay líneas en el log» no distinguía entre «corrió y no había nada» y
    # «lleva días sin correr». Sale como mucho una línea por vuelta, y solo cuando
    # de verdad ha consultado a alguien.
    if nombres or mirados:
        log.info("recien_llegados: %d nombres, %d en listas, %d en espera, %d en la ventana",
                 nombres, mirados, saltados, len(candidatos))


async def _revisar_listas(context, db: DB, cfg: Config, session, fila, espera: int) -> bool:
    """CAS y lols.bot, que es lo que más tarde en ponerse al día."""
    user_id = fila["user_id"]
    if cfg.lols_enabled and session is not None:
        hit = await lols_det.check(user_id, session)
        if hit and await _actuar(context, db, cfg, fila, hit, espera, "lols"):
            return True
    if cfg.cas_enabled and session is not None:
        hit = await cas_det.check(user_id, session, db, cfg.cas_cache_ttl_seconds)
        if hit and (hit.payload or {}).get("offenses", 0) >= cfg.cas_autoban_min:
            if await _actuar(context, db, cfg, fila, hit, espera, "cas"):
                return True
    return False


async def _actuar(context, db: DB, cfg: Config, fila, hit, espera: int, origen: str) -> bool:
    """Aplica el mismo criterio que en el join, incluida la protección al veterano."""
    from .handlers import _apply_action, _trust_score_cached
    chat_id: int = fila["chat_id"]
    user_id: int = fila["user_id"]
    trust = _trust_score_cached(context, db, chat_id, user_id)
    if trust >= 90:
        # Igual que en el join: un veterano fichado por una lista externa huele a
        # falso positivo de la lista, no a spammer. Se anota y decide un humano.
        log.warning("recien_llegados: %s user=%s trust=%d → no se autobanea", origen, user_id, trust)
        db.log_action(
            chat_id=chat_id, user_id=user_id, username=fila["username"], message_id=None,
            rule=f"{hit.rule}_trusted_review", action="noop", score=hit.score, mode=cfg.mode,
            payload={"trust": trust, "would_be": "ban", "via": "recien_llegados"},
        )
        return True
    log.info(
        "recien_llegados: %s fichó a user=%s %ds después de entrar (aún sin escribir) → ban",
        origen, user_id, espera,
    )
    decision = decide([hit], cfg.ban_score, cfg.kick_score, cfg.mute_score,
                      cfg.first_msg_attack_action, is_first_msg_attack=False)
    await _apply_action(
        context, db, cfg, chat_id=chat_id, chat_title=fila["chat_title"],
        user_id=user_id, username=fila["username"], message_id=None,
        decision=decision, original_text=None, first_name=fila["first_name"],
    )
    return True


def _toca_leer_perfil(context, chat_id: int, user_id: int) -> bool:
    """¿Toca gastar una lectura de perfil por Telethon en esta persona?

    Dos frenos: el presupuesto de la vuelta y una espera larga por persona. Sin
    ellos, 25 revisiones por ciclo serían 25 lecturas de perfil cada cuarto de
    hora contra la cuenta secundaria, que es justo la forma de ganarse un
    FloodWait y quedarse sin ninguna señal.
    """
    if context.bot_data.get(_CLAVE_PRESUPUESTO, 0) <= 0:
        return False
    cache = context.bot_data.setdefault(_CLAVE_PERFILES, {})
    ahora = time.time()
    if ahora - cache.get((chat_id, user_id), 0.0) < RELECTURA_PERFIL_S:
        return False
    cache[(chat_id, user_id)] = ahora
    for clave, visto in list(cache.items()):
        if ahora - visto > VENTANA_S:
            del cache[clave]
    context.bot_data[_CLAVE_PRESUPUESTO] -= 1
    return True


async def _revisar_perfil(context, db: DB, cfg: Config, fila, espera: int) -> bool:
    """¿Hay algo en el perfil que al entrar le habría costado la entrada?

    Se pregunta a Telegram por el nombre ACTUAL (`get_chat_member`, una llamada
    barata de la Bot API). Si ese nombre ya dispara por sí solo, se lee el perfil
    por Telethon para decidir entre banear y dejar mudo: el salvoconducto de
    «cuenta antigua con foto» tiene que valer aquí exactamente igual que en el
    join, o estaríamos siendo más duros por la puerta de atrás con un
    chino-hablante legítimo que se cambió el nombre.

    Y aunque el nombre esté limpio se lee el perfil de vez en cuando (con
    presupuesto, ver `_toca_leer_perfil`), porque el nombre no es el único
    escaparate: el CANAL enlazado en el perfil se puede poner después de entrar y
    no se ve desde la Bot API. Caso medido: «Vickycat46», nombre latino y foto
    normal, con un canal chino reclutando mulas de blanqueo.
    """
    from . import user_signals, verification
    from .handlers import _apply_action
    chat_id, user_id = fila["chat_id"], fila["user_id"]

    try:
        miembro = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramError as exc:
        log.debug("recien_llegados: no se pudo leer al miembro %s: %s", user_id, exc)
        return False
    usuario = miembro.user
    if usuario is None or usuario.is_bot:
        return False

    obvio, _razones = verification._is_obvious_spam_profile(
        None, usuario.username, usuario.first_name, usuario.last_name,
    )
    if not obvio and not _toca_leer_perfil(context, chat_id, user_id):
        return False

    sig = None
    reporter = context.bot_data.get("reporter")
    client = reporter.get_client() if reporter else None
    if client is not None:
        try:
            sig = await user_signals.fetch(client, user_id, chat_id=chat_id,
                                           first_name=usuario.first_name)
        except Exception as exc:  # noqa: BLE001
            log.debug("recien_llegados: sin señales de %s: %s", user_id, exc)

    # El canal del perfil, que es lo que no se ve desde la Bot API. Va antes que
    # el resto porque puede disparar con el nombre completamente limpio.
    if sig is not None and sig.personal_channel_title:
        if await _revisar_canal(context, db, cfg, fila, usuario, sig, client, espera):
            return True

    if not obvio:
        return False

    obvio, razones = verification._is_obvious_spam_profile(
        sig, usuario.username, usuario.first_name, usuario.last_name,
    )
    if obvio:
        log.info(
            "recien_llegados: user=%s cambió su perfil tras entrar (%ds) → ban directo",
            user_id, espera,
        )
        from .scoring import Decision
        await _apply_action(
            context, db, cfg, chat_id=chat_id, chat_title=fila["chat_title"],
            user_id=user_id, username=usuario.username, message_id=None,
            decision=Decision(
                action="ban", score=200, rule="obvious_spam_profile",
                reason=t("alert.obvious_spam") + " | ".join(
                    verification.render_reason_list(razones)[:3]),
                payload={"reasons": razones, "via": "recien_llegados", "espera_s": espera},
            ),
            original_text=None, first_name=usuario.first_name,
        )
        return True

    if not cfg.shadow and verification.han_requiere_decision(
            sig, usuario.username, usuario.first_name, usuario.last_name):
        log.info("recien_llegados: user=%s con nombre Han y salvoconducto → mudo", user_id)
        db.log_action(
            chat_id=chat_id, user_id=user_id, username=usuario.username, message_id=0,
            rule="han_pending_review", action="mute", score=0, mode="active",
            payload={"motivo": "nombre en Han puesto tras entrar", "via": "recien_llegados"},
        )
        chat = getattr(miembro, "chat", None)
        if chat is None:
            try:
                chat = await context.bot.get_chat(chat_id)
            except TelegramError:
                return False
        exito = await verification.restringir_seguro(
            context.bot, db, chat_id, user_id, verification.MUTED_PERMISSIONS,
            motivo="han tras entrar",
        )
        if exito:
            await verification.avisar_han_mudo(context, db, cfg, chat, usuario, sig)
        return True
    return False


async def _revisar_canal(context, db: DB, cfg: Config, fila, usuario, sig, client,
                         espera: int) -> bool:
    """El canal enlazado en el perfil, con los MISMOS criterios que en el join.

    Se reutiliza el helper del handler entero (título primero, y solo si no basta
    se lee lo que publica el canal) para que no haya dos varas de medir: lo que
    aquí se banea es exactamente lo que se habría baneado al entrar.
    """
    from .handlers import _apply_action, _chat_allowed_scripts, _mirar_canal_personal
    chat_id, user_id = fila["chat_id"], fila["user_id"]
    try:
        hit = await _mirar_canal_personal(
            client, sig, usuario,
            allowed_scripts=_chat_allowed_scripts(db, chat_id, cfg),
        )
    except Exception as exc:  # noqa: BLE001 — un trabajo de fondo nunca tumba el bot
        log.debug("recien_llegados: canal de %s ilegible: %s", user_id, exc)
        return False
    if not hit:
        return False

    log.info(
        "recien_llegados: user=%s tenía un canal de spam en el perfil (%ds sin escribir) → ban",
        user_id, espera,
    )
    from .scoring import Decision
    await _apply_action(
        context, db, cfg, chat_id=chat_id, chat_title=fila["chat_title"],
        user_id=user_id, username=usuario.username, message_id=None,
        decision=Decision(
            action="ban", score=hit.score, rule=hit.rule, reason=hit.reason,
            payload={**(hit.payload or {}), "via": "recien_llegados", "espera_s": espera},
        ),
        original_text=None, first_name=usuario.first_name,
    )
    return True
