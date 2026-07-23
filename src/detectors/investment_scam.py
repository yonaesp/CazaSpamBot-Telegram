"""Detector: testimonio de estafa de inversión ("le di X y me devolvió mucho más").

Patrón real que motivó el detector (primer mensaje, en un grupo en inglés):
  "Mrs RafaelMarrero7 has been so good to me. I gave her 25,000 Rs, and after
   12 hours, she gave me 318,000Rs. 👇 @RafaelMarrero7"

Ese mensaje SOLO lo cazaba `external_mention` por la @mención del final. Sin la
mención se colaba: no hay enlace t.me/, "Rs" no es una moneda de la lista de
`commercial_ad`, y no tiene la estructura multilínea con emojis del anuncio
laboral. La firma AQUÍ es otra: el RELATO de "entregué dinero → me devolvieron
mucho más", casi siempre con un plazo ("en 12 horas") y el elogio a una
"gestora"/experto. Un humano normal no cuenta eso en su primer mensaje.

Diseño (mismo espíritu que `commercial_ad`, señales acumuladas):

  PUERTA OBLIGATORIA — el mensaje debe contener a la vez un verbo de ENTREGA
  (invertí/di/envié/deposité...) y un verbo de RETORNO (me devolvió/gané/
  retiré/"gave me"...). Sin las dos mitades del relato no se evalúa nada: eso
  descarta de un plumazo "te envié el dinero", "invertí en mi formación", etc.

  Sobre esa base se suma score por: ganancia DIRECCIONAL (lo devuelto > lo
  entregado; es LA señal), dos cifras de dinero, elogio a un benefactor/experto,
  plazo de rentabilidad, y llamada a contactar. Bonus de primer mensaje.

Anti falso positivo (regla nº1 del proyecto: mejor dejar pasar spam que banear a
un legítimo):
  - "le di 50€ al camarero y me devolvió 5 de cambio" NO dispara: hay relato y
    dos cifras, pero lo devuelto (5) es MENOR que lo entregado (50) → sin
    ganancia; base+dos_cifras+primer_msg se queda por debajo del umbral.
  - "invertí en mi negocio y generó ingresos" no llega: sin cifras ni ganancia
    direccional se queda en la base.
  - El empresario legítimo que cuenta cifras reales cae en la red de seguridad:
    no es HARD_RULE, así que el trust protege (>=70 se ignora) y el trust medio
    (40-69) va a REVISIÓN humana en vez de ban automático.
"""
from __future__ import annotations

import re
import unicodedata

from telegram import Message

from ..i18n import t
from . import Hit

# --- Verbos de ENTREGA de dinero (lado del que "invierte") -------------------
# Bilingüe (es/en). Nota: "gave" está aquí y "gave me" en RETORNO: en la puerta
# ambos casan por separado, y para la ganancia direccional se parte por el primer
# verbo de RETORNO (ver check()), así que el orden del relato se respeta.
_INVEST_RE = re.compile(
    r"""
      \b(?:invest(?:ed|ing|s)?|gave|give|sent|send|deposit(?:ed|ing|s)?|paid|pay
          |transfer(?:red|ing|s)?|traded|trade|funded|fund)\b
    | \bput\s+in\b | \bstart(?:ed)?\s+with\b
    | \b(?:invert[ií]|invirti[oó]|invierto|entregu[eé]|deposit[eé]|mand[eé]
          |envi[eé]|pagu[eé]|transfer[ií]|puse)\b
    | \bempec[eé]\s+con\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# --- Verbos/expresiones de RETORNO (lado del que "recibe de vuelta") ----------
# "got"/"received"/"made" son palabras comunes, pero solo cuentan DENTRO de la
# puerta (junto a un verbo de entrega), así que no disparan solas.
_RETURN_RE = re.compile(
    r"""
      \b(?:gave|sent|paid|credited|transferred|deposited|returned)\s+me\b
    | \bpaid\s+me\b | \bgot\s+back\b | \bcash(?:ed)?\s+out\b
    | \b(?:earned|withdrew|withdrawn|withdraw|profited|received|made|doubled|tripled)\b
    | \bme\s+(?:dio|di[oó]|devolvi[oó]|envi[oó]|mand[oó]|pag[oó]|deposit[oó]
             |transfiri[oó]|acredit[oó]|dupl[ií]c[oó]|triplic[oó])\b
    | \b(?:gan[eé]|retir[eé]|recib[ií]|saqu[eé]|obtuve|multipliqu[eé])\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# --- Cifras de dinero -------------------------------------------------------
# Más amplia que la de commercial_ad a propósito: aquí la GUARDA es el relato, no
# la moneda, así que se aceptan "Rs"/"rupees"/"naira" (estafas del sur de Asia y
# Nigeria) y las cifras agrupadas por millares (25,000 / 25.000). Un número
# suelto pequeño como el "12" de "12 hours" NO casa (no lleva moneda ni millares).
_AMOUNT_RE = re.compile(
    r"""
      (?P<sym1>[€$£¥₽₴₹₺₩₪₦₱₲₵฿])\s*(?P<n1>\d[\d.,  ']*)          # $500
    | (?P<n2>\d[\d.,  ']*)\s*[€$£¥₽₴₹₺₩₪₦₱₲₵฿]                    # 500€
    | (?P<n3>\d[\d.,  ']*)\s*(?:k|K)\b                            # 5k
    | (?P<n4>\d[\d.,  ']*)\s*
        (?:USD|USDT|USDC|EUR|GBP|INR|PKR|NGN|Rs|rupees?|rupya|naira
           |dollars?|d[oó]lares|euros?|pounds?|rupias)\b                    # 25,000 Rs
    | (?P<n5>\d{1,3}(?:[.,  ]\d{3})+)                             # 25,000 / 25.000
    """,
    re.IGNORECASE | re.VERBOSE,
)

# --- Elogio a un benefactor / "gestor" / experto -----------------------------
_PRAISE_RE = re.compile(
    r"""
      \b(?:mrs|mr|miss|ms|sir|madam|dr)\b\.?\s+[A-Za-z]                     # Mrs Rafael...
    | \b(?:account|fund|portfolio|investment|forex|crypto|trading|financial)
        \s+(?:manager|expert|trader|advisor|adviser|analyst|coach|mentor)\b
    | \b(?:expert|professional)\s+trader\b | \b(?:trader|broker)\b
    | \bforex\b | \bbinary\s+option | \bcrypto(?:currency)?\s+(?:trad|invest|expert|min)
    | \bbitcoin\s+(?:trad|invest|min|expert)
    | (?:so|very|really|been)\s+(?:good|great|honest|kind|legit|nice)\s+to\s+me
    | \bthanks?\s+to\s+(?:her|him|mrs|mr|sir|madam|god|miss|ms)\b
    | \b(?:trust(?:ed)?|recommend(?:ed|ing)?)\s+(?:her|him)\b
    | \b(?:she|he)'?s?\s+(?:so\s+)?(?:legit|genuine|real|trustworthy|honest|reliable)\b
    | \bhighly\s+recommend | \bgod\s+bless\s+(?:her|him|you)
    | \bhelped\s+me\s+(?:earn|make|made|withdraw|invest|trade|gain|profit|to)\b
    | \b(?:sra|sr|se[ñn]ora|se[ñn]or|do[ñn]a)\b\.?\s+[A-Za-zÁÉÍÓÚÑáéíóúñ]   # Sra. Ana
    | \bgracias\s+a\s+(?:ella|[eé]l|la\s+se[ñn]ora|dios)
    | \bconf[ií][eéoó]?\s+en\s+(?:ella|[eé]l)
    | \b(?:la|lo)\s+recomiendo\b
    | \bes\s+(?:muy\s+)?(?:legal|leg[ií]tima|de\s+confianza|honesta|real|fiable)\b
    | \bme\s+ayud[oó]\s+a\s+(?:ganar|retirar|invertir|hacer)
    | \b(?:gestora?|corredora?|inversora?)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# --- Plazo de rentabilidad ("en 12 horas", "after 24 hours", "within 2 days") -
_TIME_WINDOW_RE = re.compile(
    r"""
      \b(?:after|within|in|just|only|every)\s+\d{1,3}\s*
        (?:hour|hr|day|week|minute|min|month)s?\b
    | \b\d{1,2}\s*(?:hrs?|hours?)\b
    | \b(?:en|dentro\s+de|tras|despu[eé]s\s+de|cada)\s+\d{1,3}\s*
        (?:hora|d[ií]a|semana|minuto|mes)s?\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# --- Llamada a contactar (mención, flecha 👇, "DM her", "escríbele") ----------
_CONTACT_RE = re.compile(
    r"""
      @\w{3,}
    | [\U0001F447\U0001F449\U0001F446\U0001F4E9\U0001F4B8]                  # 👇👉👆📩💸
    | \b(?:dm|pm|message|msg|contact|write|text|inbox|whatsapp|wsp)\s+
        (?:me|her|him|us|now|@|mrs|mr|to)
    | \b(?:escr[ií]be(?:le|me)?|cont[aá]cta(?:le|me|nos)?|habla\s+con|ap[uú]ntate)\b
    | \blink\s+in\s+bio\b | \bjoin\s+(?:now|us|the)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _amount_value(m: re.Match) -> int:
    """Valor numérico (solo dígitos) de una coincidencia de _AMOUNT_RE."""
    raw = m.group("n1") or m.group("n2") or m.group("n3") or m.group("n4") or m.group("n5") or ""
    digits = re.sub(r"\D", "", raw)
    return int(digits) if digits else 0


def check(msg: Message, is_first_msg: bool = False) -> Hit:
    text = (msg.text or msg.caption or "").strip()
    # NFC: unifica acentos combinados/precompuestos para que los regex con tildes
    # (devolvi[oó], invert[ií]) casen sea cual sea la forma unicode del mensaje.
    text = unicodedata.normalize("NFC", text)
    if len(text) < 25:
        return Hit.none()

    has_invest = bool(_INVEST_RE.search(text))
    return_matches = list(_RETURN_RE.finditer(text))
    # PUERTA: sin las dos mitades del relato no hay estafa de inversión que cazar.
    if not (has_invest and return_matches):
        return Hit.none()

    amounts = [(m.start(), _amount_value(m)) for m in _AMOUNT_RE.finditer(text)]
    has_two_amounts = len(amounts) >= 2

    # Ganancia DIRECCIONAL: se parte el texto por el PRIMER verbo de retorno.
    # Lo entregado son las cifras anteriores; lo recibido, las posteriores. Es
    # ganancia solo si lo recibido supera a lo entregado (25.000 → 318.000). Así
    # "le di 50 y me devolvió 5" NO cuenta como ganancia (5 < 50).
    profit = False
    rp = return_matches[0].start()
    given = [v for pos, v in amounts if pos < rp and v > 0]
    got = [v for pos, v in amounts if pos >= rp and v > 0]
    if given and got and max(got) > max(given):
        profit = True

    has_praise = bool(_PRAISE_RE.search(text))
    has_time = bool(_TIME_WINDOW_RE.search(text))
    has_contact = bool(_CONTACT_RE.search(text))

    score = 40  # base: el relato entrega→retorno ya presente (puerta superada)
    reasons: list[str] = [t("reason.inv_narrative")]
    if profit:
        score += 35
        reasons.append(t("reason.inv_profit"))
    if has_two_amounts:
        score += 12
        reasons.append(t("reason.inv_two_amounts"))
    if has_praise:
        score += 25
        reasons.append(t("reason.inv_praise"))
    if has_time:
        score += 12
        reasons.append(t("reason.inv_time_window"))
    if has_contact:
        score += 12
        reasons.append(t("reason.inv_contact"))
    if is_first_msg:
        score += 12
        reasons.append(t("reason.inv_first_msg"))

    # Umbral: la base + un par de cifras NO basta (relato ambiguo). Hace falta la
    # ganancia direccional, o el elogio/plazo/contacto que delatan el testimonio.
    if score < 70:
        return Hit.none()

    return Hit(
        rule="investment_scam",
        score=score,
        reason=t("reason.investment_scam", details=" + ".join(reasons)),
        payload={
            "profit": profit,
            "has_two_amounts": has_two_amounts,
            "has_praise": has_praise,
            "has_time_window": has_time,
            "has_contact": has_contact,
            "is_first_msg": is_first_msg,
            "score": score,
        },
    )
