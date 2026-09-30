"""El bot aprende solo de lo que pasa en sus grupos, sin IA externa.

Lo pidió el admin (30-sep-2026): «haz al bot más inteligente y autosuficiente».
De las tres vías que se le plantearon eligió las dos que no sacan nada del
servidor, y dejó fuera la de consultar a un modelo externo.

Dos piezas:

1. **Ejemplos legítimos automáticos.** El clasificador que aprende (`learning`)
   necesita ejemplos de las DOS clases y llevaba dormido desde siempre: 37 de
   spam y 0 legítimos, cuando pide 10 de cada. Aquí se guardan solos los mensajes
   corrientes de la gente asentada (trust ≥ 70) que no disparan nada. Es lo que
   hace falta para que distinga «lo que se habla en ESTE grupo» de un anuncio.

2. **Propuestas de reglas.** Cuando un admin banea a mano algo que al bot se le
   escapó, o marca un mensaje con `/spam`, el bot busca las frases de ese mensaje
   que NO aparecen en la conversación normal del grupo, las prueba contra los
   mensajes reales con la misma vista previa del panel, y le propone al admin por
   privado las que salen limpias, con un botón para activarlas. Es lo que se
   hacía a mano en cada caso nuevo.

Dos decisiones que no se deben deshacer:

- **Nada se aprende de un ban manual sin que el admin lo confirme.** Un ban no
  siempre es spam: se banea también por faltar al respeto, y aprender de eso
  enseñaría al bot a castigar insultos como si fueran anuncios. Por eso el ban
  manual solo PROPONE; es el botón el que confirma.
- **Lo automático se marca con `added_by = 0`** y se puede deshacer sin tocar lo
  que decidió el admin: si alguien de quien se guardó un ejemplo legítimo acaba
  baneado, sus ejemplos automáticos se borran.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import time
import unicodedata

from . import custom_terms, learning
from .i18n import t

log = logging.getLogger(__name__)

AUTO = 0   # `added_by` de lo que aprende el bot solo

# --- 1. Ejemplos legítimos ----------------------------------------------------
HAM_TRUST_MIN = 70           # solo gente asentada: el mismo umbral que ya la protege
HAM_MIN_CHARS = 25
HAM_MIN_PALABRAS = 5
HAM_POR_USUARIO_S = 24 * 3600   # uno por persona y día: que un charlatán no llene la clase
HAM_MAX_DIA = 40
HAM_MAX_TOTAL = 400          # `learning` solo mira los 200 más recientes de todos modos

# Enlaces y menciones no entran como ejemplo legítimo: es justo lo que un spammer
# con cuenta veterana o robada metería para «limpiar» su propio anuncio.
_ENLACE_O_MENCION = re.compile(r"(?:https?://|www\.|\bt\.me/|@[A-Za-z0-9_]{4,})", re.I)


def guardar_ham_si_procede(db, chat_id: int, user_id: int, texto: str | None,
                           trust: int, *, reenviado: bool = False) -> bool:
    """Guarda el mensaje como ejemplo legítimo si cumple TODO. Nunca lanza."""
    try:
        if trust < HAM_TRUST_MIN or reenviado or not texto:
            return False
        limpio = texto.strip()
        if len(limpio) < HAM_MIN_CHARS or len(limpio.split()) < HAM_MIN_PALABRAS:
            return False
        if _ENLACE_O_MENCION.search(limpio):
            return False
        ahora = time.time()
        if db.muestra_auto_de_usuario_desde(user_id, "ham", ahora - HAM_POR_USUARIO_S):
            return False
        if db.muestras_auto_desde("ham", ahora - 86400) >= HAM_MAX_DIA:
            return False
        norm = learning.normalize(limpio)
        nueva = db.add_sample(text_norm=norm, text_hash=learning.text_hash(norm),
                              label="ham", added_by=AUTO, chat_id=chat_id,
                              source_user=user_id)
        if nueva:
            db.recortar_muestras_auto("ham", HAM_MAX_TOTAL)
        return bool(nueva)
    except Exception as exc:  # noqa: BLE001 — aprender es un extra, jamás tumba un mensaje
        log.debug("autoaprendizaje ham user=%s: %s", user_id, exc)
        return False


def olvidar_ham_automatico(db, user_id: int) -> None:
    """Si alguien acaba baneado, lo que se aprendió de él como legítimo sobra."""
    try:
        n = db.olvidar_muestras(user_id, "ham", solo_auto=True)
        if n:
            log.info("autoaprendizaje: olvidados %d ejemplos legítimos de user=%s (baneado)",
                     n, user_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("autoaprendizaje olvidar user=%s: %s", user_id, exc)


# --- 1 bis. Ejemplos de spam de los bans SEGUROS ------------------------------
# El clasificador solo mira 90 días, y en esa ventana había UN ejemplo de spam (los
# otros 36 eran más viejos): le faltaban las dos clases, no solo la legítima.
#
# Solo aprende del TEXTO cuando fue el texto lo que delató el spam:
# - alguna regla de CONTENIDO (no de forma, que es el caso Kleo, ni de perfil: un
#   «hola» de alguien con el nombre en otro alfabeto no es un ejemplo de spam);
# - y además evidencia fuerte: 150+ puntos o una lista externa (CAS, lols).
# `learned_similarity` NO cuenta como contenido: aprender de lo que ya se parece a
# lo aprendido es un bucle que se refuerza solo.
_REGLAS_DE_CONTENIDO = frozenset({
    "commercial_ad", "investment_scam", "url_blocklist", "contact_spam",
    "offplatform_contact", "link_target_spam", "tg_deeplink",
    "inline_buttons_from_user", "external_mention_or_link",
})
_LISTAS_EXTERNAS = frozenset({"cas_match", "lols_match"})
SPAM_MIN_SCORE = 150
SPAM_MIN_CHARS = 20


def aprender_spam_de_ban(db, chat_id: int, user_id: int, texto: str | None,
                         reglas: str, score: int) -> bool:
    """Guarda el texto de un ban seguro como ejemplo de spam. Nunca lanza."""
    try:
        if not texto or len(texto.strip()) < SPAM_MIN_CHARS:
            return False
        rs = set((reglas or "").split("+"))
        if not rs & _REGLAS_DE_CONTENIDO:
            return False
        if score < SPAM_MIN_SCORE and not rs & _LISTAS_EXTERNAS:
            return False
        norm = learning.normalize(texto)
        return bool(db.add_sample(text_norm=norm, text_hash=learning.text_hash(norm),
                                  label="spam", added_by=AUTO, chat_id=chat_id,
                                  source_user=user_id))
    except Exception as exc:  # noqa: BLE001
        log.debug("autoaprendizaje spam user=%s: %s", user_id, exc)
        return False


def olvidar_spam_automatico(db, user_id: int) -> None:
    """Al desbanear a alguien, lo que el bot aprendió SOLO de él como spam sobra.
    Lo que marcó el admin a mano se respeta: fue una decisión suya."""
    try:
        n = db.olvidar_muestras(user_id, "spam", solo_auto=True)
        if n:
            log.info("autoaprendizaje: olvidados %d ejemplos de spam de user=%s (desbaneado)",
                     n, user_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("autoaprendizaje olvidar spam user=%s: %s", user_id, exc)


# --- 2. Propuestas de reglas --------------------------------------------------
# Van a la lista de anuncios ilegales del panel: una coincidencia suma 35, que
# SOLA no llega a actuar (35 + primer mensaje 15 = 50 < 60). Refuerza, no decide.
PROPUESTA_FICHERO = "commercial_illegal_services.txt"
PROPUESTA_MAX = 3
CANDIDATOS_MAX = 40
VENTANA_TEXTOS_S = 7 * 86400
_CLAVE = "rprop_"


def _palabras_vacias() -> frozenset[str]:
    return learning._STOPWORDS_ES | learning._STOPWORDS_EN


def candidatos(texto: str) -> list[str]:
    """Frases de 2 y 3 palabras seguidas del mensaje, en el orden en que salen.

    Solo las que el término literal volvería a encontrar en el propio mensaje:
    proponer algo que no casaría con el spam que lo motivó no sirve de nada.
    """
    vacias = _palabras_vacias()
    fuera: list[str] = []
    vistos: set[str] = set()
    norm = unicodedata.normalize("NFKC", texto or "")
    for linea in norm.splitlines():
        palabras = re.findall(r"\w+", linea.lower())
        for n in (3, 2):
            for i in range(len(palabras) - n + 1):
                trozo = palabras[i:i + n]
                if all(p in vacias for p in trozo) or all(p.isdigit() for p in trozo):
                    continue
                if any(len(p) < 2 for p in trozo):
                    continue
                frase = " ".join(trozo)
                if frase in vistos or len(frase) < custom_terms.MIN_TERM_LEN:
                    continue
                vistos.add(frase)
                try:
                    if not custom_terms.compile_literal(frase, filename=PROPUESTA_FICHERO).search(norm):
                        continue
                except Exception:  # noqa: BLE001
                    continue
                fuera.append(frase)
    return fuera


def _vocabulario(db) -> set[str]:
    palabras: set[str] = set()
    for txt in db.textos_legitimos():
        palabras.update(re.findall(r"\w+", unicodedata.normalize("NFKC", txt).lower()))
    return palabras


def _palabra_rara(frase: str, vocabulario: set[str]) -> bool:
    """¿Lleva alguna palabra que NUNCA se ha dicho en la conversación legítima?

    Es el filtro que importa. La vista previa solo mira ~300 mensajes, y con tan
    poca muestra casi cualquier frase sale limpia: al probarlo con una pregunta
    normal («¿por qué no me aparece el PC en la red local?») proponía «no me
    aparece», y del spam de Adobe proponía «office pro plus», que en un grupo de
    Windows es conversación corriente. Pedir una palabra ajena al grupo es la
    misma idea de discordancia que usa el resto del bot.
    """
    return any(len(p) >= 4 and not p.isdigit() and p not in vocabulario
               for p in frase.split())


def elegir(db, textos: list[str]) -> list[dict]:
    """Las mejores frases: con alguna palabra ajena al grupo, limpias contra lo
    real, y mejor si ya salían en otro spam."""
    spam_previo = [s.lower() for s in (db.recent_sample_texts(label="spam", limit=200,
                                                              since_days=365) or [])]
    propios = {learning.normalize(x).lower() for x in textos}
    ajenos = [s for s in spam_previo if s not in propios]
    vistas: list[str] = []
    for texto in textos:
        for c in candidatos(texto):
            if c not in vistas:
                vistas.append(c)
    vocabulario = _vocabulario(db)
    vistas = [v for v in vistas if _palabra_rara(v, vocabulario)]
    buenas: list[dict] = []
    for frase in vistas[:CANDIDATOS_MAX]:
        vista = custom_terms.preview_term(db, PROPUESTA_FICHERO, frase)
        if not vista.valid.ok or vista.matches or vista.ham_hits:
            continue
        en_otros = sum(1 for s in ajenos if frase in s)
        # La condición que manda: la frase ya salió en OTRO spam confirmado. Una
        # sola aparición no dice nada (con ~300 mensajes de muestra casi todo sale
        # «limpio»); dos spams distintos que la repiten, y nunca la conversación
        # normal, sí. Con un spam de un tipo nuevo no se propone nada: se aprende
        # el ejemplo, y la frase se propondrá cuando vuelva una variante.
        if en_otros < 1:
            continue
        buenas.append({"term": vista.term, "revisados": vista.scanned,
                       "en_otros": en_otros, "n": len(frase.split())})
    buenas.sort(key=lambda d: (-d["en_otros"], -d["n"], -len(d["term"])))
    # Si dos frases se solapan («redeem code» y «adobe redeem code»), sobra la corta.
    buenas = [d for d in buenas
              if not any(d is not o and d["term"] in o["term"] for o in buenas)]
    return buenas[:PROPUESTA_MAX]


def _textos_de(db, user_id: int) -> list[str]:
    filas = db.textos_recientes_de(user_id, time.time() - VENTANA_TEXTOS_S)
    return [txt for _c, _m, txt in filas if txt and len(txt.strip()) >= 10][:3]


async def proponer_reglas(context, db, cfg, user_id: int, chat_id: int,
                          motivo: str, textos: list[str] | None = None) -> bool:
    """Manda al admin por privado lo que podría aprender. Nunca lanza."""
    try:
        destino = getattr(cfg, "admin_notify_chat_id", None) or cfg.admin_user_id
        if not destino:
            return False
        textos = [x for x in (textos or _textos_de(db, user_id)) if x]
        if not textos:
            return False
        elegidas = elegir(db, textos)
        pid = secrets.token_hex(4)
        db.set_text_pref(_CLAVE + pid, json.dumps(
            {"u": user_id, "c": chat_id, "terms": [e["term"] for e in elegidas],
             "texts": [x[:500] for x in textos], "ts": time.time()}, ensure_ascii=False))
        await context.bot.send_message(
            chat_id=destino, parse_mode="HTML", disable_web_page_preview=True,
            text=_texto_propuesta(motivo, user_id, textos[0], elegidas),
            reply_markup=_botones(pid, [e["term"] for e in elegidas]))
        log.info("autoaprendizaje: propuesta %s user=%s motivo=%s terminos=%s",
                 pid, user_id, motivo, [e["term"] for e in elegidas])
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("autoaprendizaje: no se pudo proponer para user=%s: %s", user_id, exc,
                    exc_info=True)
        return False


def _texto_propuesta(motivo: str, user_id: int, texto: str, elegidas: list[dict]) -> str:
    import html
    lineas = []
    for e in elegidas:
        extra = t("auto.prop_en_otros", n=e["en_otros"]) if e["en_otros"] else ""
        lineas.append(t("auto.prop_linea", term=html.escape(e["term"]),
                        revisados=e["revisados"], extra=extra))
    cuerpo = "\n".join(lineas) if lineas else t("auto.prop_sin_terminos")
    return t("auto.prop_dm", motivo=html.escape(motivo), uid=user_id,
             texto=html.escape(texto[:300]), terminos=cuerpo)


def _botones(pid: str, terms: list[str]):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    # Los ya aplicados se quedan como hueco ("") para no descolocar los índices.
    filas = [[InlineKeyboardButton(t("auto.btn_termino", term=term[:40]),
                                   callback_data=f"rprop:t:{pid}:{i}")]
             for i, term in enumerate(terms) if term]
    filas.append([
        InlineKeyboardButton(t("auto.btn_solo_msg"), callback_data=f"rprop:m:{pid}"),
        InlineKeyboardButton(t("auto.btn_no"), callback_data=f"rprop:x:{pid}"),
    ])
    return InlineKeyboardMarkup(filas)


def _guardar_spam(db, datos: dict, admin_id: int) -> int:
    n = 0
    for texto in datos.get("texts") or []:
        norm = learning.normalize(texto)
        if norm and db.add_sample(text_norm=norm, text_hash=learning.text_hash(norm),
                                  label="spam", added_by=admin_id, chat_id=datos.get("c"),
                                  source_user=datos.get("u")):
            n += 1
    return n


async def on_callback(update, context) -> None:
    """Botones de la propuesta. Solo el admin del bot."""
    q = update.callback_query
    if q is None:
        return
    cfg = context.bot_data["cfg"]
    db = context.bot_data["db"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer(t("hdl.only_admin_review"))
        return
    partes = (q.data or "").split(":")
    if len(partes) < 3:
        await q.answer()
        return
    accion, pid = partes[1], partes[2]
    crudo = db.get_text_pref(_CLAVE + pid)
    if not crudo:
        await q.answer(t("auto.caducada"), show_alert=True)
        return
    datos = json.loads(crudo)
    if accion == "x":
        db.set_text_pref(_CLAVE + pid, "")
        await q.answer(t("auto.toast_no"))
        await _cerrar(q, t("auto.suf_no"))
        return
    # Pulsar un término o «solo el mensaje» ES la confirmación de que era spam.
    n = _guardar_spam(db, datos, q.from_user.id)
    if accion == "m":
        db.set_text_pref(_CLAVE + pid, "")
        await q.answer(t("auto.toast_msg", n=n))
        await _cerrar(q, t("auto.suf_msg", n=n))
        return
    if accion == "t" and len(partes) == 4 and partes[3].isdigit():
        i = int(partes[3])
        terms = datos.get("terms") or []
        if i >= len(terms) or not terms[i]:
            await q.answer(t("auto.ya_hecho"))
            return
        res = custom_terms.add_term(PROPUESTA_FICHERO, terms[i])
        hecho = terms[i]
        terms[i] = ""
        datos["terms"] = terms
        db.set_text_pref(_CLAVE + pid, json.dumps(datos, ensure_ascii=False))
        if res.ok:
            log.info("autoaprendizaje: término aprendido «%s» (propuesta %s)", hecho, pid)
            await q.answer(t("auto.toast_termino", term=hecho[:60]))
        else:
            await q.answer(t("auto.toast_termino_err", code=res.code), show_alert=True)
        try:
            await q.edit_message_reply_markup(reply_markup=_botones(pid, [x for x in terms]))
        except Exception:  # noqa: BLE001
            pass
        return
    await q.answer()


async def _cerrar(q, sufijo: str) -> None:
    try:
        await q.edit_message_text((q.message.text_html or q.message.text or "") + sufijo,
                                  parse_mode="HTML", disable_web_page_preview=True)
    except Exception:  # noqa: BLE001
        pass
