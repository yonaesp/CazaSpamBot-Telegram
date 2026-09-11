"""Detector: testimonio de estafa de multiplicación de dinero.

El patrón, calcado del caso real:
  «Mrs RafaelMarrero7 has been so good to me. I gave her 25,000 Rs, and after
   12 hours, she gave me 318,000 Rs. 👇 @RafaelMarrero7»

Antes solo lo cazaba `external_mention_or_link` por el @usuario final. Sin esa
mención se colaba entero: no tiene estructura de anuncio (ni líneas con emoji ni
CTA clásico), así que `commercial_ad` puntuaba 0, y al estar en inglés tampoco
saltaba `non_allowed_script`.

La señal FUERTE no es «dinero»: gente normal habla de dinero constantemente. Es la
DISCORDANCIA del testimonio: «di X y me devolvieron Y», con Y bastante mayor que X.
Eso casi nadie lo dice en serio. Aun así, el ancla sola NO basta (alguien podría
contar que invirtió 1000 y ahora vale 1500): hace falta ADEMÁS una señal propia de
la estafa (elogio a la persona que te hace ganar, o llamada a contactarla).

Las monedas exóticas (Rs, ₹, ₦, PKR, USDT...) NO son de por sí spam: solo suman
cuando ya hay estructura de testimonio. El importe se detecta pegado a una cifra.
"""
from __future__ import annotations

import re

from telegram import Message

from ..i18n import t
from ..wordlists import load_and_compile
from . import Hit

# --- Ancla: "di X ... me devolvieron Y" con Y > X ---------------------------
# Verbos de ENTREGA (yo puse el dinero) y de RETORNO (me lo devolvieron mayor).
# "worth" queda FUERA de los de retorno a propósito: "invested 1000, now worth
# 1500" es lenguaje legítimo de inversión, no un testimonio de estafa.
_GIVE = r"(?:gave|sent|invested|deposited|paid|put\s+in|transferred|traded\s+with|di|invert[ií]|deposit[eé]|envi[eé]|puse)"
_BACK = r"(?:got|received|gave\s+me|earned|made|withdrew|withdraw|cashed\s+out|returned|profit(?:ed)?|recib[ií]|me\s+(?:dio|devolvi[oó]| envi[oó])|gan[eé]|retir[eé])"

# Un importe: cifra + moneda (símbolo o código) delante o detrás. La cifra admite
# separadores de miles (25,000 / 25.000 / 25 000) Y números pegados (5000, 45000):
# la primera versión solo cogía los que llevaban separador y partía «5000» en «500».
# Incluye monedas de varias regiones porque esta estafa circula en inglés global.
_CUR = r"(?:Rs\.?|₹|INR|PKR|₦|naira|NGN|USDT?|USD|\$|€|EUR|£|GBP|BTC|ETH|K|k)"
_NUMCORE = r"\d+(?:[.,\s]\d{3})*(?:[.,]\d+)?"
_AMOUNT = rf"(?:{_CUR}\s*)?({_NUMCORE})\s*(?:{_CUR})?"

# Estructura entrega -> retorno, tolerante a lo que haya en medio (nombre, tiempo).
_GIVE_BACK_RE = re.compile(
    rf"\b{_GIVE}\b[^.\n]{{0,60}}?{_AMOUNT}[^.\n]{{0,80}}?\b{_BACK}\b[^.\n]{{0,60}}?{_AMOUNT}",
    re.IGNORECASE,
)

# --- Ancla 2: testimonio de REVERSIÓN, sin una sola cifra -------------------
# «pensé que era una estafa, pero el dinero llegó». Caso real (11-sep-2026,
# Windows 10): «Saw your post and honestly thought it was a scam, but the money
# actually came through and I'm in shock». Ni cifras, ni @usuario, ni enlace: el
# ancla numérica no casaba, `commercial_ad` daba 0 y al estar en inglés tampoco
# saltaba `non_allowed_script`. El detector entero puntuaba **0** y lo tuvo que
# borrar y banear un admin a mano.
#
# Es la otra mitad del mismo timo: uno publica el anzuelo y un segundo perfil
# responde haciéndose pasar por cliente satisfecho. Por eso llega DÍAS después de
# entrar (esta cuenta entró el 7 y escribió el 11) y por eso no lleva enlace: el
# enlace lo pone el otro.
#
# La señal fuerte, igual que en el ancla numérica, es la DISCORDANCIA: admitir que
# se sospechaba una estafa y a continuación decir que el dinero llegó. Es
# estructural, no vocabulario, así que NO se externaliza a config/.
_SKEPTIC = (
    r"(?:thought\s+(?:it|this|that|they)\s+(?:was|were)\s+(?:a\s+)?(?:scam|fake|joke|lie)"
    r"|was\s+(?:very\s+|so\s+)?(?:skeptical|sceptical|doubtful|unsure)"
    r"|did(?:n't|\s+not)\s+(?:believe|think)\s+(?:it|this|that)"
    r"|pens[eé]\s+que\s+(?:era|ser[ií]a)\s+(?:una\s+)?(?:estafa|timo|mentira)"
    r"|no\s+me\s+lo\s+cre[ií]a|dudaba\s+(?:mucho|de)"
    r"|cre[ií]\s+que\s+era\s+(?:una\s+)?(?:estafa|timo))"
)
_PAYOUT = (
    r"(?:(?:money|payment|payout|funds?|cash|profits?)\s+(?:\w+\s+){0,3}?"
    r"(?:came\s+through|arrived|landed|hit\s+my|was\s+real|is\s+real)"
    r"|got\s+(?:paid|my\s+(?:money|payout|profit))"
    r"|(?:it|this)\s+(?:actually|really)\s+(?:works?|worked|paid)"
    r"|(?:received|withdrew|cashed\s+out)\s+(?:the\s+|my\s+)?(?:money|payment|profit)"
    r"|(?:lleg[oó]|entr[oó])\s+el\s+dinero|me\s+(?:pagaron|lo\s+pagaron)"
    r"|s[ií]\s+(?:funciona|pag[oó]|era\s+real))"
)
# El conector de reversión es obligatorio: sin él, «pensé que era una estafa» y
# «me pagaron» pueden ser dos frases de conversaciones distintas del mismo párrafo.
_SKEPTIC_FLIP_RE = re.compile(
    rf"{_SKEPTIC}[^.\n]{{0,90}}?\b(?:but|yet|however|pero|aunque|sin\s+embargo)\b[^.\n]{{0,90}}?{_PAYOUT}",
    re.IGNORECASE,
)

# --- Señales propias de la estafa (una es obligatoria además del ancla) ------
# Las tres listas de vocabulario que siguen son EDITABLES por el admin desde
# config/blacklist/ (genéricas + por idioma + custom), igual que las de
# commercial_ad. Los defaults de abajo son el juego COMPLETO (español E inglés)
# a propósito: esta estafa circula sobre todo en inglés, así que sin la carpeta
# config/ el bot debe seguir cazándola idéntico a como lo hacía hardcodeado. El
# reparto español = archivo genérico / inglés = en/ es solo para poder editar
# cada idioma por separado; NO afecta al comportamiento con los archivos puestos.
#
# NO se toca el ancla (_GIVE_BACK_RE / _give_back_multiplier) ni _TIME_RE: son
# lógica estructural del núcleo del detector, no vocabulario, y no deben editarse.

# Elogio a la persona que "te hace ganar". No es un "gracias" cualquiera: es la
# fórmula del testimonio. Por eso pide "thanks TO" (con to) + persona, no "thanks John".
# boundaries=True: cada alternativa empieza y acaba en palabra, así que el
# envoltorio \b(?:...)\b reproduce EXACTAMENTE el regex original.
_DEFAULT_PRAISE = [
    r"has\s+been\s+(?:so\s+)?(?:good|kind|honest|amazing|wonderful)\s+to\s+me",
    r"changed\s+my\s+life",
    r"(?:she|he|she's|he's|shes|hes)\s+(?:is\s+)?(?:so\s+)?(?:legit|real|honest|trustworthy|genuine|the\s+best)",
    r"trust(?:ed)?\s+(?:her|him|mrs|mr|ms|madam|sir)",
    r"thanks?\s+to\s+(?:her|him|mrs|mr|ms|madam|sir|god)",
    r"god\s+bless\s+(?:her|him|you)",
    r"i\s+(?:highly\s+)?recommend\s+(?:her|him|mrs|mr|ms)",
    r"forever\s+grateful",
    r"gracias\s+a\s+(?:ella|el|él|la\s+se[ñn]ora|don|do[ñn]a)",
    r"me\s+cambi[oó]\s+la\s+vida",
    r"es\s+(?:muy\s+)?(?:legal|honesta?|de\s+confianza|real)",
]

# Llamada a contactar a esa persona (el destino del testimonio).
# boundaries=False: los emojis (👇👉📲) van FUERA de cualquier \b (junto a un
# emoji, \b nunca casaría), así que cada patrón de texto lleva su propio \b y los
# emojis quedan sueltos. Reproduce el original \b(?:...)\b|👇|👉|📲.
_DEFAULT_CTA = [
    r"\b(?:dm|pm|message|contact|write|reach\s+out\s+to|inbox)\s+(?:her|him|mrs|mr|ms|now|@)\b",
    r"\b(?:join|start|invest)\s+(?:now|with|today)\b",
    r"\blink\s+in\s+bio\b",
    r"\bescr[ií]be(?:le|nos)?\b",
    r"\bcont[aá]cta(?:la|lo|le)?\b",
    r"\b[uú]nete\s+(?:ya|ahora|hoy)\b",
    r"👇",
    r"👉",
    r"📲",
]

# Vocabulario de reclutamiento (plataforma/programa de "inversión garantizada").
# boundaries=True: mismo caso que _DEFAULT_PRAISE.
_DEFAULT_VOCAB = [
    r"binary\s+option",
    r"forex",
    r"crypto\s+(?:trad|invest|mining)",
    r"trading\s+(?:signal|platform|expert|account)",
    r"account\s+manager",
    r"expert\s+trader",
    r"investment\s+(?:platform|plan|program|opportunity)",
    r"double\s+your\s+(?:money|investment|capital)",
    r"guaranteed\s+(?:profit|return|income)",
    r"passive\s+income",
    r"withdraw(?:al)?\s+(?:proof|instant)",
    r"se[ñn]ales\s+de\s+trading",
    r"inversi[oó]n\s+garantizada",
    r"duplica\s+tu\s+(?:dinero|inversi[oó]n)",
]


# Fórmulas del testimonio en primera persona: el asombro de quien dice haber
# cobrado y la referencia al mensaje ajeno al que responde. Por sí solas no
# deciden nada (ver la guarda de dos señales): «no me lo puedo creer» lo dice
# cualquiera. boundaries=True, como _DEFAULT_PRAISE.
_DEFAULT_TESTIMONY = [
    r"(?:i'?m|im|i\s+am)\s+(?:still\s+)?in\s+shock",
    r"still\s+(?:can'?t|cannot)\s+believe",
    r"can'?t\s+believe\s+(?:it|this|my\s+eyes)",
    r"saw\s+(?:your|his|her|the)\s+(?:post|message|comment|testimony)",
    r"(?:it|this)\s+(?:really|actually)\s+works?",
    r"(?:no\s+me\s+lo\s+puedo\s+creer|a[uú]n\s+no\s+me\s+lo\s+creo)",
    r"vi\s+(?:tu|su)\s+(?:publicaci[oó]n|mensaje|post|comentario)",
    r"de\s+verdad\s+funciona",
]


def _testimony_re() -> re.Pattern:
    return load_and_compile("investment_testimony.txt", _DEFAULT_TESTIMONY)


def _praise_re() -> re.Pattern:
    return load_and_compile("investment_praise.txt", _DEFAULT_PRAISE)


def _cta_re() -> re.Pattern:
    return load_and_compile("investment_cta.txt", _DEFAULT_CTA, boundaries=False)


def _vocab_re() -> re.Pattern:
    return load_and_compile("investment_vocab.txt", _DEFAULT_VOCAB)

# Elemento temporal: "after 12 hours", "within 24h", "in 2 days". Refuerza, no decide.
_TIME_RE = re.compile(
    r"\b(?:after|within|in|en|tras|despu[eé]s\s+de)\s+\d{1,3}\s*"
    r"(?:hours?|hrs?|h|days?|d|minutes?|mins?|horas?|d[ií]as?|minutos?)\b",
    re.IGNORECASE,
)


def _to_number(raw: str) -> float:
    """'318,000' / '25.000' / '25 000' -> float, tolerando separadores mixtos."""
    s = re.sub(r"[.,\s]", "", raw)
    return float(s) if s.isdigit() else 0.0


def _give_back_multiplier(text: str) -> float:
    """Devuelve Y/X si hay patrón entrega->retorno con Y>X, si no 0."""
    m = _GIVE_BACK_RE.search(text)
    if not m:
        return 0.0
    dado, vuelto = _to_number(m.group(1)), _to_number(m.group(2))
    if dado <= 0 or vuelto <= 0:
        return 0.0
    return vuelto / dado


def _cita(m) -> str:
    """El trozo EXACTO que hizo saltar la señal, listo para enseñárselo al admin.

    Las etiquetas genéricas («elogio a quien te hace ganar») dejaron de describir lo
    que pasa desde que las listas cubren más formas de este timo: en el caso real
    saltaba por «legendary whale» y «only 100 spots left», y el motivo hablaba de
    contactar a una persona, cosa que ese mensaje no pedía. Y ese texto es lo que el
    admin lee al revisar un ban meses después.

    Se limpian `<`, `>` y `&` en vez de escaparlos: el motivo pasa luego por sitios
    que ya escapan HTML, y escapar dos veces le enseñaría al admin «&amp;lt;».
    """
    import re as _re
    trozo = _re.sub(r"\s+", " ", m.group(0)).strip()
    trozo = trozo.translate({ord(c): None for c in "<>&"})
    return trozo[:40] + ("…" if len(trozo) > 40 else "")


def check(msg: Message, is_first_msg: bool = False) -> Hit:
    text = (getattr(msg, "text", None) or getattr(msg, "caption", None) or "").strip()
    if len(text) < 25:
        return Hit.none()

    score = 0
    reasons: list[str] = []

    # ANCLA 1: "di X y me devolvieron Y", con Y al menos 1.5x. Es la firma del timo.
    mult = _give_back_multiplier(text)
    tiene_ancla_num = mult >= 1.5
    if tiene_ancla_num:
        score += 45
        reasons.append(t("reason.invscam_giveback", mult=f"{mult:.0f}"))

    # ANCLA 2: "pensé que era una estafa, pero el dinero llegó". Mismo peso: es
    # igual de específica, solo que sin cifras.
    m_flip = _SKEPTIC_FLIP_RE.search(text)
    tiene_flip = bool(m_flip)
    if tiene_flip:
        score += 45
        reasons.append(t("reason.invscam_flip", q=_cita(m_flip)))
    tiene_ancla = tiene_ancla_num or tiene_flip

    m_testimony = _testimony_re().search(text)
    tiene_testimony = bool(m_testimony)
    if tiene_testimony:
        score += 30
        reasons.append(t("reason.invscam_testimony", q=_cita(m_testimony)))

    m_praise = _praise_re().search(text)
    m_cta = _cta_re().search(text)
    m_vocab = _vocab_re().search(text)
    tiene_praise, tiene_cta, tiene_vocab = bool(m_praise), bool(m_cta), bool(m_vocab)

    if tiene_praise:
        score += 30
        reasons.append(t("reason.invscam_praise", q=_cita(m_praise)))
    if tiene_cta:
        score += 25
        reasons.append(t("reason.invscam_cta", q=_cita(m_cta)))
    if tiene_vocab:
        score += 20
        reasons.append(t("reason.invscam_vocab", q=_cita(m_vocab)))

    # Refuerzos que NUNCA deciden solos: solo suman si ya hay estructura de timo.
    hay_estructura = tiene_ancla or tiene_praise or tiene_cta or tiene_vocab or tiene_testimony
    if hay_estructura:
        if _TIME_RE.search(text):
            score += 10
            reasons.append(t("reason.invscam_time"))
        # Primer mensaje: esta estafa entra y suelta el testimonio de golpe.
        if is_first_msg:
            score += 10
            reasons.append(t("reason.invscam_firstmsg"))

    # GUARDA ANTI-FP: una sola señal jamás basta. Sin el ancla numérica hacen
    # falta DOS señales propias de la estafa; con el ancla, una. Así "invertí
    # 1000 y ahora vale 1500" (solo ancla) no llega, y "gracias John, me
    # ayudaste" (solo un gracias suelto) tampoco.
    señales_estafa = sum((tiene_ancla_num, tiene_flip, tiene_praise, tiene_cta,
                          tiene_vocab, tiene_testimony))
    if señales_estafa < 2:
        return Hit.none()

    if score < 60:
        return Hit.none()

    return Hit(
        rule="investment_scam",
        score=score,
        reason=t("reason.investment_scam", details=" + ".join(reasons)),
        payload={
            "multiplier": round(mult, 1),
            "skeptic_flip": tiene_flip,
            "testimony": tiene_testimony,
            "praise": tiene_praise,
            "cta": tiene_cta,
            "vocab": tiene_vocab,
            "first_msg": is_first_msg,
            "score": score,
        },
    )
