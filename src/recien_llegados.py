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

from telegram.error import RetryAfter, TelegramError

from .config import Config
from .db import DB
from .detectors import cas as cas_det
from .detectors import lols_bot as lols_det
from .i18n import t
from .scoring import decide

log = logging.getLogger(__name__)

# Cuánto tiempo se vigila a alguien que acaba de entrar.
#
# Estuvo en 24 h con el razonamiento de que «el peor caso medido tardó 27 h en
# escribir, y ya estaba fichado a las 24». La red respondió midiéndonos: el
# 7688429577 entró con el perfil limpio (la traza del join lo prueba: señales
# leídas, sin canal), dejó pasar la ventana entera, se puso el nombre
# `六o0壹天` y el canal de la red YA FUERA de vigilancia, y escribió a las
# **29,6 h** de entrar. Contra un adversario que se adapta, cualquier ventana
# corta es un plazo que se puede esperar; una semana obliga a mantener la
# cuenta dormida tanto tiempo que deja de salirles a cuenta.
#
# El coste se mantiene a raya con DOS cadencias (abajo): el primer día se mira
# a ritmo caliente, y del segundo al séptimo a ritmo frío. Medido al cambiarlo:
# 142 personas calladas en 7 días (27 de ellas en el primer día).
VENTANA_S = 7 * 24 * 3600
# El primer día tras entrar: vigilancia a ritmo caliente. Es cuando escriben
# casi todos los que van a escribir.
FRESCO_S = 24 * 3600
# Espera mínima entre dos consultas a listas externas sobre la misma persona.
RECHEQUEO_S = 3600
RECHEQUEO_FRIO_S = 6 * 3600
# Consultas a listas externas (CAS, lols) por vuelta. Con el trabajo cada 15 min
# son 100 a la hora como techo.
MAX_POR_CICLO = 25

# Nombres leídos por vuelta. Cubre la ventana ENTERA en cada vuelta porque esto
# es Bot API: gratis, sin límite práctico y sin tocar la cuenta secundaria
# (142 nombres cada 15 min son ~0,16 llamadas/s). El tope existe solo para que
# una avalancha no convierta una vuelta en mil llamadas seguidas. Ojo: la
# consulta ordena por join más reciente, así que si la ventana superara este
# tope, los más antiguos serían los que quedasen sin mirar.
MAX_NOMBRES_POR_CICLO = 200

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
# Con una hora y ~27 candidatos en el primer día salen ~27 lecturas a la hora,
# que entran en el presupuesto. Si la ventana creciera mucho, el presupuesto la
# degrada sola y algunos esperan un poco más.
RELECTURA_PERFIL_S = 3600
# Pasado el primer día, ritmo frío: el perfil completo se relee cada 6 h. El
# NOMBRE se sigue mirando en cada vuelta (es gratis), así que el cambio de
# nombre se caza en ≤15 min también en frío; lo que se espacia es solo la
# lectura por Telethon (canal, bio, fotos). Con ~115 personas frías salen ~19
# lecturas/h, que sumadas a las calientes rozan el presupuesto justo.
RELECTURA_PERFIL_FRIA_S = 6 * 3600

_CLAVE_CACHE = "_recien_llegados_visto"
_CLAVE_PERFILES = "_recien_llegados_perfil"
_CLAVE_PRESUPUESTO = "_recien_llegados_presupuesto"


def _toca_mirar(context, chat_id: int, user_id: int, espera: int = 0) -> bool:
    """¿Ha pasado ya el tiempo mínimo desde la última consulta sobre esta persona?

    `espera` son los segundos que lleva dentro: el primer día se consulta cada
    hora, después cada 6 (las listas son APIs de terceros y la ventana es de una
    semana; sin el ritmo frío seríamos su mayor cliente).

    En memoria a propósito: perderlo al reiniciar solo cuesta unas consultas de
    más, y no merece una columna nueva en la base de datos.
    """
    cache = context.bot_data.setdefault(_CLAVE_CACHE, {})
    ahora = time.time()
    plazo = RECHEQUEO_S if espera <= FRESCO_S else RECHEQUEO_FRIO_S
    if ahora - cache.get((chat_id, user_id), 0.0) < plazo:
        return False
    cache[(chat_id, user_id)] = ahora
    # Nada anterior a la ventana vuelve a hacer falta.
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

    # El armado, para la ventana entera: el primer día lo mira cada minuto
    # `vigilar_armado_job`; del segundo al séptimo basta con esta vuelta (L63).
    try:
        await _vigilar_armado(context, VENTANA_S, MAX_NOMBRES_POR_CICLO)
    except Exception as exc:  # noqa: BLE001
        log.warning("armado: fallo en la pasada del repaso: %s", exc)

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
        if not _toca_mirar(context, chat_id, user_id, espera):
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
        leidos = MAX_PERFILES_POR_CICLO - context.bot_data.get(_CLAVE_PRESUPUESTO, 0)
        log.info("recien_llegados: %d nombres, %d perfiles leídos, %d consultados en listas, "
                 "%d en espera, %d en la ventana",
                 nombres, leidos, mirados, saltados, len(candidatos))


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
        from types import SimpleNamespace
        from .handlers import _revision_humana
        lista = "lols.bot" if hit.rule.startswith("lols") else "CAS"
        await _revision_humana(
            context, db, cfg, SimpleNamespace(id=chat_id, title=db.titulo_chat(chat_id)),
            SimpleNamespace(id=user_id, username=fila["username"], first_name=fila["first_name"]),
            [("lista_externa_veterano", {"lista": lista, "trust": trust})])
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


def _toca_leer_perfil(context, chat_id: int, user_id: int, espera: int = 0) -> bool:
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
    plazo = RELECTURA_PERFIL_S if espera <= FRESCO_S else RELECTURA_PERFIL_FRIA_S
    if ahora - cache.get((chat_id, user_id), 0.0) < plazo:
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

    # ¿Se ha cambiado el nombre desde la última vez que lo vimos? Se registra y se
    # guarda el nuevo.
    #
    # Sin esta traza no había forma de responder «¿lo miramos y no saltó, o es que
    # cambió justo antes de escribir?». Pasó el 1-sep-2026 con el 8846717922: entró
    # a las 06:28 con un nombre que no disparaba, escribió a las 09:21 llamándose
    # `电我煮叶` y lo cazó el chequeo del primer mensaje. Entre medias se le miró el
    # nombre unas once veces sin que saltara nada, así que el cambio tuvo que ser
    # de los últimos minutos, pero eso era una deducción, no un dato.
    #
    # `seen_users.first_name` solo se escribía al hablar, así que de quien todavía
    # no ha escrito no teníamos ningún nombre guardado con el que comparar.
    try:
        previo = (fila["first_name"] or "") if "first_name" in fila.keys() else ""
        actual = usuario.first_name or ""
        if actual and actual != previo:
            if previo:
                log.info("recien_llegados: user=%s se ha cambiado el nombre: %r → %r",
                         user_id, previo[:40], actual[:40])
            db.actualizar_nombre_visto(chat_id, user_id, actual)
    except Exception as exc:  # noqa: BLE001 — una traza jamás frena la revisión
        log.debug("recien_llegados: no se pudo comparar el nombre de %s: %s", user_id, exc)

    _permitidos = verification.allowed_scripts_de(db, fila["chat_id"], cfg)
    obvio, _razones = verification._is_obvious_spam_profile(
        None, usuario.username, usuario.first_name, usuario.last_name,
        allowed_scripts=_permitidos,
    )
    if not obvio and not _toca_leer_perfil(context, chat_id, user_id, espera):
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

    # La bio, con el mismo detector que en el join. Se descargaba y no se miraba:
    # la puesta después de entrar, o la de una red cuyo enlace aparece en otra
    # cuenta días más tarde, no se veía nunca (Helen, Gloria y Brook, 31-oct-2026).
    if sig is not None and sig.bio:
        from .detectors import bio_spam
        hit = bio_spam.check(sig.bio, db=db, user_id=user_id)
        if hit:
            log.info("recien_llegados: user=%s bio de spam (%ds tras entrar) → ban directo: %s",
                     user_id, espera, hit.reason[:200])
            from .scoring import Decision
            await _apply_action(
                context, db, cfg, chat_id=chat_id, chat_title=fila["chat_title"],
                user_id=user_id, username=usuario.username, message_id=None,
                decision=Decision(
                    action="ban", score=hit.score, rule=hit.rule, reason=hit.reason,
                    payload={**hit.payload, "via": "recien_llegados", "espera_s": espera},
                ),
                original_text=None, first_name=usuario.first_name,
            )
            return True
        if await revisar_destino_bio(context, db, cfg, chat_id, fila["chat_title"], usuario,
                                     sig.bio, "recien_llegados"):
            return True

    # Los «Posts» del perfil, el escaparate que más cabe (pie + OCR de la foto).
    if await _revisar_posts(context, db, cfg, fila, usuario, sig, client, espera):
        return True

    # El criterio del join ENTERO en cuanto hay perfil leído, no solo cuando el
    # nombre ya disparaba: la bio o el título del canal en un alfabeto que el chat
    # no permite cuentan igual con el nombre limpio (L63). Sin perfil leído, el
    # nombre solo ya dijo que no.
    por_nombre = obvio
    if not por_nombre and sig is None:
        return False

    obvio, razones = verification._is_obvious_spam_profile(
        sig, usuario.username, usuario.first_name, usuario.last_name,
        allowed_scripts=_permitidos,
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

    # Lo de abajo (dejar mudo un nombre Han con salvoconducto) sigue siendo solo
    # para un nombre que dispara: con el nombre limpio no hay nada que decidir, y
    # a quien el admin ya dejó pasar no se le vuelve a silenciar en cada lectura.
    if not por_nombre:
        return False

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


async def _revisar_posts(context, db: DB, cfg: Config, fila, usuario, sig, client,
                         espera: int, via: str = "recien_llegados") -> bool:
    """Los «Posts» del perfil (historias fijadas), juzgados por `posts_perfil`.

    Solo si `GetFullUser` dice que los hay (`sig.tiene_posts`): quien no tiene no
    cuesta ni una llamada. Leerlos con OCR lleva segundos, así que esto se llama
    solo desde trabajos de fondo, nunca en la ruta de un mensaje.
    """
    if sig is None or not getattr(sig, "tiene_posts", False) or client is None:
        return False
    from . import posts_reader
    from .detectors import posts_perfil
    from .handlers import _apply_action
    from .wordlists import modo_ocr
    chat_id, user_id = fila["chat_id"], fila["user_id"]
    posts = await posts_reader.leer(client, sig.entidad, user_id)
    if not posts:
        return False
    # `modo_ocr` es un indicador global: dentro no puede haber ningún await.
    with modo_ocr():
        hit = posts_perfil.check([p.texto for p in posts])
    if not hit:
        return False
    if db.is_banned(user_id):
        return True
    log.info("%s: user=%s posts del perfil de spam (%ds tras entrar) → ban: %s",
             via, user_id, espera, hit.reason[:200])
    from .scoring import Decision
    await _apply_action(
        context, db, cfg, chat_id=chat_id, chat_title=fila["chat_title"],
        user_id=user_id, username=usuario.username, message_id=None,
        decision=Decision(
            action="ban", score=hit.score, rule=hit.rule, reason=hit.reason,
            payload={**(hit.payload or {}), "via": via, "espera_s": espera},
        ),
        original_text=None, first_name=usuario.first_name,
    )
    return True


# Espera antes de juzgar los posts tras un join: deja que el flujo del join
# (bienvenida, verificación) termine antes de banear, para que no quede una
# bienvenida publicada para alguien ya baneado. Leer los posts con OCR tarda más
# que esto casi siempre; sin fotos, la lista llega en 0,1 s.
_ESPERA_JOIN_S = 5.0


async def revisar_posts_aparte(context, chat, user, sig, client, via: str = "join") -> bool:
    """Tarea aparte para los posts del perfil (join y primer mensaje). True si se actuó.

    En el join no se puede esperar al OCR: PTB procesa los updates de uno en uno
    y diez fotos son varios segundos sin moderar nada. Así sale en paralelo y el
    join sigue su camino. Caso que lo motivó: ZERO, baneado a mano por otro admin
    dos minutos después de entrar; el repaso de recién llegados habría tardado
    hasta 15 min.
    """
    import asyncio
    try:
        await asyncio.sleep(_ESPERA_JOIN_S)
        db: DB = context.bot_data["db"]
        cfg: Config = context.bot_data["cfg"]
        fila = {"chat_id": chat.id, "chat_title": getattr(chat, "title", None),
                "user_id": user.id, "username": user.username,
                "first_name": user.first_name}
        if db.is_banned(user.id):
            return False
        # El repaso de dentro de 15 min no repite el trabajo: `posts_reader`
        # guarda la lectura una hora y el OCR de cada post para siempre.
        return await _revisar_posts(context, db, cfg, fila, user, sig, client, 0, via)
    except Exception as exc:  # noqa: BLE001 — una tarea suelta nunca tumba el bot
        log.warning("revisar_posts_aparte: fallo con user=%s: %s", user.id, exc)
        return False


# ---------------------------------------------------------------------------
# La bio con un enlace privado que no llega a `bio_spam` (L58)
# ---------------------------------------------------------------------------

# Regla de la fila `noop` que deja la revisión: sirve de traza y de «ya avisado».
REGLA_REVISION_BIO = "bio_enlace_privado"


async def revisar_destino_bio(context, db: DB, cfg: Config, chat_id: int, chat_title: str | None,
                              user, bio: str | None, via: str) -> bool:
    """Bio con un enlace privado (t.me/+…) que `bio_spam` no basta para banear: se lee
    adónde lleva, sin entrar ni contar como visita, y se juzga con `link_target`. Si el
    destino se confiesa spam o su título está en un alfabeto que el grupo no permite,
    ban; si sale limpio o no se puede leer, revisión humana al privado, una sola vez
    por persona. True si se baneó. Nunca lanza.

    Caso que lo motivó (8-nov-2026, Alexa): entró el 28-oct con solo un enlace privado
    en la bio (40 puntos, el umbral es 60), pasó el botón en 47 s y once días después
    publicó un testimonio de inversión. Las 20 cuentas vistas con un enlace privado en
    la bio eran spam; de 600 veteranos repasados, ninguno lo lleva.
    """
    from .detectors import bio_spam, link_target
    try:
        codigos = bio_spam.enlaces_privados(bio)
        if not codigos:
            return False
        from . import link_reader
        from .handlers import _apply_action, _revision_humana, _se_modera
        destino = await link_reader.leer(context, [f"https://t.me/+{c}" for c in codigos])
        if destino is not None and destino.chat_id is not None and _se_modera(db, cfg, destino.chat_id):
            return False                 # lleva a uno de nuestros grupos
        hit = link_target.check(destino)
        titulo = (destino.titulo if destino else "") or ""
        puntos, motivo, alfabeto = (hit.score, hit.reason, None) if hit else (0, None, None)
        if not hit and titulo:
            # El destino no se confiesa, pero su título está escrito en un alfabeto que
            # este grupo no permite: el mismo criterio que el nombre, la bio y el canal
            # personal, y aquí con un enlace privado delante (decisión del admin,
            # 12-nov-2026, L62: «公群 2714 -墨颜集团色料代收 押金28888U» fue a revisión).
            from . import verification
            otro = verification._texto_en_otro_alfabeto(
                titulo, verification.allowed_scripts_de(db, chat_id, cfg))
            if otro:
                alfabeto = otro[0]
                puntos, motivo = 60, t("reason.destino_otro_alfabeto", alfabeto=alfabeto)
        if motivo:
            from .scoring import Decision
            log.info("bio con enlace privado user=%s chat=%s destino=%r → %s, ban (%s)",
                     user.id, chat_id, titulo[:80],
                     f"en otro alfabeto ({alfabeto})" if alfabeto else "SPAM", via)
            payload = {"bio_preview": bio[:200], "destino": titulo[:200],
                       "url": getattr(destino, "url", None), "via": via}
            if alfabeto:
                payload["destino_alfabeto"] = alfabeto
            await _apply_action(
                context, db, cfg, chat_id=chat_id, chat_title=chat_title,
                user_id=user.id, username=user.username, message_id=None,
                decision=Decision(
                    action="ban", score=min(200, 40 + puntos), rule="bio_spam",
                    reason=t("reason.bio_spam", details=t("reason.bio_invite_link") + " + " + motivo),
                    payload=payload,
                ),
                original_text=None, first_name=user.first_name,
            )
            return True
        if db.tiene_accion(user.id, REGLA_REVISION_BIO):
            return False
        log.info("bio con enlace privado user=%s chat=%s destino=%r → revisión humana (%s)",
                 user.id, chat_id, titulo[:80] or None, via)
        db.log_action(
            chat_id=chat_id, user_id=user.id, username=user.username, message_id=None,
            rule=REGLA_REVISION_BIO, action="noop", score=40, mode=cfg.mode,
            payload={"bio_preview": bio[:200], "destino": titulo[:200] or None,
                     "via": via, "would_be": "review"},
        )
        motivo = (("bio_enlace_privado", {"destino": titulo[:80]}) if titulo
                  else ("bio_enlace_privado_ilegible", {}))
        from types import SimpleNamespace
        await _revision_humana(
            context, db, cfg, SimpleNamespace(id=chat_id, title=chat_title or db.titulo_chat(chat_id)),
            user, [motivo])
        return False
    except Exception as exc:  # noqa: BLE001 — nunca frena la entrada ni el repaso
        log.warning("revisar_destino_bio: fallo con user=%s: %s", getattr(user, "id", "?"), exc)
        return False


async def revisar_destino_bio_aparte(context, chat, user, bio: str) -> bool:
    """La de arriba en una tarea aparte para el join: leer el destino es una llamada
    por la cuenta secundaria y PTB procesa los updates de uno en uno."""
    import asyncio
    try:
        await asyncio.sleep(_ESPERA_JOIN_S)
        db: DB = context.bot_data["db"]
        if db.is_banned(user.id):
            return False
        return await revisar_destino_bio(context, db, context.bot_data["cfg"], chat.id,
                                         getattr(chat, "title", None), user, bio, "join")
    except Exception as exc:  # noqa: BLE001
        log.warning("revisar_destino_bio_aparte: fallo con user=%s: %s", user.id, exc)
        return False


# ---------------------------------------------------------------------------
# Disparador: alguien se ha cambiado el nombre AHORA MISMO
# ---------------------------------------------------------------------------
# El repaso de arriba es un barrido periódico, o sea que siempre llega con un
# retraso de hasta 15 minutos. Pero MTProto tiene `updateUserName`, que avisa en
# el momento. La Bot API NO lo entrega (sus `chat_member` son cambios de ESTADO:
# entrar, salir, ban, promote; un cambio de perfil no genera ninguno), así que
# esta vía solo existe con Telethon conectado.
#
# La documentación oficial no dice para QUÉ usuarios llega ese update, así que
# esto es a la vez la defensa y el experimento: si Telegram lo entrega para
# miembros de un supergrupo, el cambio de nombre se caza en segundos en lugar de
# en minutos; si no lo entrega, no se dispara nunca y el barrido periódico sigue
# siendo la defensa. No se pierde nada por tenerlo.
#
# El update NO decide nada: solo dice «mira a este ya». Toda la lógica sigue en
# `_revisar_perfil`, para que no haya dos varas de medir.

_CLAVE_DISPARO = "_recien_llegados_disparo"
# Ventana mínima entre dos revisiones disparadas por la misma persona. Un cambio
# de nombre puede llegar repetido (o en ráfaga si juegan con ello) y no vamos a
# leerle el perfil por Telethon en bucle.
DISPARO_CADA_S = 120


async def revisar_ahora(context, user_id: int, motivo: str = "cambio de nombre",
                        forzar: bool = False) -> bool:
    """Revisa a una persona concreta fuera de turno. True si se actuó.

    Best-effort de principio a fin: esto lo llama un handler de Telethon, y un
    fallo aquí no puede tumbar el listener ni el bot.

    `forzar` se salta la espera entre disparos: lo usa la vigilancia del armado,
    que ya trae su propio tope por persona (`MAX_DISPAROS_ARMADO`) y no puede
    perder el segundo cambio de una ráfaga (foto, y un minuto después la bio).
    """
    db: DB = context.bot_data.get("db")
    cfg: Config = context.bot_data.get("cfg")
    if db is None or cfg is None:
        return False
    if db.is_banned(user_id):
        return False

    cache = context.bot_data.setdefault(_CLAVE_DISPARO, {})
    ahora = time.time()
    if not forzar and ahora - cache.get(user_id, 0.0) < DISPARO_CADA_S:
        return False
    cache[user_id] = ahora
    for clave, visto in list(cache.items()):
        if ahora - visto > VENTANA_S:
            del cache[clave]

    try:
        filas = db.vigilancia_de(user_id, ahora - VENTANA_S)
    except Exception as exc:  # noqa: BLE001
        log.warning("revisar_ahora: no se pudo consultar a %s: %s", user_id, exc)
        return False
    if not filas:
        return False

    # El barrido periódico tiene sus propios frenos por persona; aquí se saltan a
    # propósito, porque el disparo ya es la prueba de que algo cambió.
    for fila in filas:
        clave = (fila["chat_id"], user_id)
        context.bot_data.setdefault(_CLAVE_PERFILES, {}).pop(clave, None)
    if context.bot_data.get(_CLAVE_PRESUPUESTO, 0) <= 0:
        context.bot_data[_CLAVE_PRESUPUESTO] = 1

    actuado = False
    for fila in filas:
        if actuado and db.is_banned(user_id):
            break                      # el ban es federado: los demás grupos ya lo tienen
        espera = int(ahora - float(fila["join_ts"]))
        try:
            if await _revisar_perfil(context, db, cfg, fila, espera):
                actuado = True
                log.info("revisar_ahora: user=%s cazado por %s (%ds dentro)",
                         user_id, motivo, espera)
                continue
            # Las listas también, sin esperar a su hora: quien se arma el perfil
            # suele haber soltado ya el spam en otro grupo (L63: lols fichó a las
            # dos cuentas 4 minutos antes de que escribieran aquí).
            context.bot_data.setdefault(_CLAVE_CACHE, {})[(fila["chat_id"], user_id)] = ahora
            if await _revisar_listas(context, db, cfg, context.bot_data.get("http"), fila, espera):
                actuado = True
                log.info("revisar_ahora: user=%s fichado en las listas tras %s (%ds dentro)",
                         user_id, motivo, espera)
        except Exception as exc:  # noqa: BLE001
            log.warning("revisar_ahora: fallo con user=%s chat=%s: %s",
                        user_id, fila["chat_id"], exc)
    return actuado


# ---------------------------------------------------------------------------
# El armado: entrar con el perfil vacío y ponérselo minutos antes de escribir
#
# Caso medido (13-nov-2026, Windows 10): «Cortney» entró a las 04:38 sin foto,
# sin @ y sin bio, y lols.bot no la tenía. A las 07:56 ya llevaba la foto, el @
# y la bio de la red, y lols la fichó (había escrito en otro grupo); a las 08:00
# escribió aquí. El repaso había pasado a las 07:49 y volvía a las 08:04: la
# cazó el primer mensaje, un segundo después de publicarlo. «Tabitha», igual 50 s
# antes. Y dentro quedaban 24 cuentas más con el perfil vacío, esperando.
#
# Leer el perfil más a menudo con la cuenta secundaria no es el camino (regla 9),
# pero no hace falta: `getChat` de la Bot API da la bio, la foto, el @ y el canal
# personal de cualquier miembro, gratis y sin tocar esa cuenta (medido: 0,06-0,5 s
# por llamada, también de una cuenta ya baneada). Con eso se mira cada minuto si
# el perfil ha CAMBIADO, y solo entonces se gasta la lectura completa.
#
# El cambio NO decide nada, igual que `updateUserName` (que en cinco días no ha
# llegado ni una vez): solo dice «mira a este ya», y deciden los criterios de
# siempre en `_revisar_perfil`, más las listas.
# ---------------------------------------------------------------------------

# Cada cuánto corre la vigilancia del primer día. Los dos casos medidos dejaron
# al menos 3,5 y 4,6 minutos entre armarse y escribir aquí.
ARMADO_CADA_S = 60
# Personas por pasada. Una llamada por persona: 80 al minuto son 1,3 por segundo
# de techo, muy por debajo de lo que la Bot API admite.
MAX_ARMADO_POR_PASADA = 80
# Revisiones completas que puede provocar la misma persona. Quien juegue a
# cambiarse el perfil en bucle no convierte esto en una lectura por minuto con
# la cuenta secundaria: agotado el tope, vuelve al ritmo del repaso.
MAX_DISPAROS_ARMADO = 6
# Si Telegram pide frenar, la vigilancia se aparta este tiempo. Un 429 para
# TODAS las peticiones del bot (L61): antes ciegos un rato aquí que lentos al banear.
ARMADO_PAUSA_S = 900

_CLAVE_HUELLAS = "_recien_llegados_huella"
_CLAVE_ARMADO = "_recien_llegados_armado"
_CAMPOS_HUELLA = ("nombre", "usuario", "bio", "foto", "canal")


def _huella(chat) -> tuple[str, str, str, str, str]:
    """Lo que se ve del perfil desde la Bot API, en el orden de `_CAMPOS_HUELLA`."""
    foto = getattr(chat, "photo", None)
    canal = getattr(chat, "personal_chat", None)
    return (
        " ".join(p for p in (getattr(chat, "first_name", None),
                             getattr(chat, "last_name", None)) if p),
        getattr(chat, "username", None) or "",
        getattr(chat, "bio", None) or "",
        str(getattr(foto, "big_file_unique_id", None) or "sí") if foto else "",
        str(getattr(canal, "id", None) or "sí") if canal else "",
    )


async def vigilar_armado_job(context) -> None:
    """Cada minuto: ¿alguien del primer día se ha cambiado el perfil?"""
    try:
        await _vigilar_armado(context, FRESCO_S, MAX_ARMADO_POR_PASADA)
    except Exception as exc:  # noqa: BLE001 — un trabajo de fondo nunca tumba el bot
        log.warning("armado: fallo en la pasada: %s", exc)


async def _vigilar_armado(context, ventana_s: int, limite: int) -> int:
    """Compara el perfil de cada vigilado con el de la pasada anterior. Devuelve los cambios."""
    import asyncio
    db: DB = context.bot_data.get("db")
    if db is None or context.bot_data.get("cfg") is None:
        return 0
    # El primer latido sale a los 5 minutos de arrancar (y después, uno por hora):
    # tras un reinicio se ve enseguida que la vigilancia corre y puede leer.
    estado = context.bot_data.setdefault(_CLAVE_ARMADO, {
        "pausa": 0.0, "latido": time.time() - 3300, "consultas": 0, "cambios": 0,
        "fallos": 0, "disparos": {}, "cerrojo": asyncio.Lock(),
    })
    # La pasada del minuto y la del repaso comparten las huellas: de una en una,
    # o el mismo cambio dispararía dos revisiones.
    async with estado["cerrojo"]:
        ahora = time.time()
        if ahora < estado["pausa"]:
            return 0
        huellas = context.bot_data.setdefault(_CLAVE_HUELLAS, {})
        cambios = 0
        vistos: set[int] = set()
        for fila in db.recien_llegados_callados(ahora - ventana_s, limite=limite * 2):
            user_id = fila["user_id"]
            if user_id in vistos or len(vistos) >= limite:
                continue
            vistos.add(user_id)
            if db.is_banned(user_id):
                continue
            try:
                chat = await context.bot.get_chat(user_id)
            except RetryAfter as exc:
                pide = getattr(exc, "retry_after", 0)
                pide = pide.total_seconds() if hasattr(pide, "total_seconds") else float(pide or 0)
                estado["pausa"] = time.time() + max(ARMADO_PAUSA_S, pide)
                log.warning("armado: Telegram pide frenar %.0f s: vigilancia en pausa %d min",
                            pide, int(max(ARMADO_PAUSA_S, pide) // 60))
                break
            except TelegramError as exc:
                estado["fallos"] += 1
                log.debug("armado: no se pudo leer a %s: %s", user_id, exc)
                continue
            estado["consultas"] += 1
            nueva = _huella(chat)
            previa = huellas.get(user_id)
            huellas[user_id] = (nueva, ahora)
            if previa is None or previa[0] == nueva:
                continue
            campos = "+".join(c for c, a, b in zip(_CAMPOS_HUELLA, previa[0], nueva) if a != b)
            hechos = estado["disparos"].get(user_id, 0)
            if hechos >= MAX_DISPAROS_ARMADO:
                continue
            estado["disparos"][user_id] = hechos + 1
            estado["cambios"] += 1
            cambios += 1
            log.info("armado: user=%s ha cambiado %s a los %ds de entrar → se revisa ya",
                     user_id, campos, int(ahora - float(fila["join_ts"])))
            await revisar_ahora(context, user_id, motivo=f"cambio de perfil ({campos})", forzar=True)

        for user_id, (_h, visto) in list(huellas.items()):
            if ahora - visto > VENTANA_S:
                del huellas[user_id]
                estado["disparos"].pop(user_id, None)
        # Latido, una línea a la hora: sin ella «no hay líneas» no distingue entre
        # «nadie cambió nada» y «lleva días sin correr o sin poder leer a nadie».
        if ahora - estado["latido"] >= 3600:
            log.info("armado: %d perfiles vigilados, %d consultas, %d sin respuesta y %d cambios desde el último latido",
                     len(huellas), estado["consultas"], estado["fallos"], estado["cambios"])
            if estado["fallos"] and not estado["consultas"]:
                # No poder mirar no es «nadie cambió nada».
                log.warning("armado: ninguna consulta ha respondido en la última hora (%d fallos): "
                            "no se está vigilando a nadie", estado["fallos"])
            estado.update(latido=ahora, consultas=0, cambios=0, fallos=0)
        return cambios
