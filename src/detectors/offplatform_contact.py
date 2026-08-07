"""Detector: «este es mi número de OTRA app, escríbeme ahí».

Caso real que lo originó (07/08/2026, grupo de Windows 10). Cuenta nueva, catorce
minutos después de entrar, primer y único mensaje:

    Este es mi número de Zangi; puedes escribirme ahí ahora mismo 👉👉 7702361204
    Zangi 👉
    Cariño, este es mi nuevo número de Zangi: 3476746619. Escríbeme ahora 💞❤️❤️

Ni un enlace, ni una @mención, ni un alfabeto raro: **ningún detector tenía nada
que mirar**. Se quedó una hora y cuarto en el grupo hasta que un admin lo borró a
mano. Es el patrón de entrada del timo romántico y de la estafa de inversión: sacar
a la víctima de Telegram, donde nadie modera, antes de pedirle nada.

Diseño, calcado del molde de `investment_scam`:

- **La señal fuerte no es el tema, es la discordancia.** Dar un teléfono no es spam
  (en un grupo de soporte pasa), y decir «escríbeme por privado» tampoco. Lo raro
  es la combinación: un número **de otra aplicación** más una llamada a seguir la
  conversación **allí**. El ancla es esa estructura, no una palabra suelta.
- **Ninguna señal decide sola.** Sin ancla no se mira nada más; con ancla hace falta
  al menos un apoyo. Así «mi whatsapp es 600123456» a secas NO cae, que es justo el
  mensaje legítimo que más se le parece.
- **El primer mensaje solo refuerza**, nunca decide: suma si ya hay estructura.

Los tres apoyos son deliberadamente distintos entre sí, para que no se disparen los
tres por lo mismo: redirección explícita, gancho afectivo y «número nuevo» (el
clásico de quien se hace pasar por un contacto conocido).
"""
from __future__ import annotations

import re

from telegram import Message

from ..i18n import t
from ..wordlists import load_and_compile
from . import Hit

# Pesos. El ancla sola se queda por debajo de MUTE_SCORE (40) a propósito: si no
# hay ni un apoyo, el detector ni siquiera emite.
SCORE_ANCLA = 50
SCORE_REDIRECCION = 30
SCORE_GANCHO = 25
SCORE_NUMERO_NUEVO = 25
SCORE_PRIMER_MENSAJE = 25   # refuerzo, nunca decide

# Un teléfono, no un número cualquiera. Entre 7 y 15 dígitos (E.164), sin pegarse a
# letras ni a un punto decimal: así «la build 22621.1234» o «el 0.1» no cuentan.
_TELEFONO_RE = re.compile(r"(?<![\w.])\+?\d[\d\s.()-]{5,17}\d(?![\w])")

# Corazones y besos. Dos o más = gancho afectivo. Uno suelto lo pone cualquiera.
_CORAZONES_RE = re.compile(
    "[❤\U0001f495-\U0001f49f\U0001f48b\U0001f618\U0001f60d\U0001f970\U0001f63b]")

_APPS_DEFAULT = [
    # Mensajeros fuera de Telegram. Los nombres son iguales en todos los idiomas,
    # por eso esta lista no tiene variante por idioma.
    r"zangi", r"botim", r"viber", r"whats?app", r"wasap", r"wsp", r"wa\.me",
    r"wechat", r"weixin", r"kakaotalk", r"skype", r"snapchat", r"hangouts",
    r"facetime", r"imessage", r"signal", r"messenger",
]

_CTA_DEFAULT = [
    # Redirección EXPLÍCITA: «ahí», «allí», «ahora». Sin ese adverbio no es una
    # redirección, es un «escríbeme» normal y corriente, que no prueba nada.
    r"escr[íi]b[ei]me\s+(?:por\s+)?(?:ah[íi]|all[íi]|all[áa]|ahora)",
    r"escribirme\s+(?:ah[íi]|all[íi]|ahora)",
    r"cont[áa]ctame\s+(?:ah[íi]|all[íi]|ahora)",
    r"h[áa]blame\s+(?:por\s+)?(?:ah[íi]|all[íi])",
    r"agr[ée]game\s+(?:ah[íi]|all[íi])",
    r"b[úu]scame\s+(?:ah[íi]|all[íi])",
]

_GANCHO_DEFAULT = [
    r"cari[ñn]o", r"mi\s+amor", r"mi\s+vida", r"mi\s+cielo", r"beb[ée]",
    r"guap[oa]", r"preciosa", r"linda",
]

# «Este es mi NUEVO número»: el que se hace pasar por un contacto que cambió de
# teléfono. Va aparte de los demás apoyos porque es una señal de otra naturaleza.
_NUMERO_NUEVO_DEFAULT = [
    r"nuevo\s+n[úu]mero", r"n[úu]mero\s+nuevo", r"cambi[ée]\s+de\s+n[úu]mero",
    r"new\s+number", r"changed\s+my\s+number",
]


def _apps_re():
    return load_and_compile("offplatform_apps.txt", _APPS_DEFAULT)


def _cta_re():
    return load_and_compile("offplatform_cta.txt", _CTA_DEFAULT)


def _gancho_re():
    return load_and_compile("offplatform_hook.txt", _GANCHO_DEFAULT)


def _numero_nuevo_re():
    return load_and_compile("offplatform_newnumber.txt", _NUMERO_NUEVO_DEFAULT)


def _tiene_telefono(texto: str) -> bool:
    for m in _TELEFONO_RE.finditer(texto):
        digitos = sum(c.isdigit() for c in m.group(0))
        if 7 <= digitos <= 15:
            return True
    return False


def check(msg: Message, is_first_msg: bool = False) -> Hit:
    texto = (getattr(msg, "text", None) or getattr(msg, "caption", None) or "")
    if not texto.strip():
        return Hit.none()

    app = _apps_re().search(texto)
    if not app or not _tiene_telefono(texto):
        return Hit.none()          # sin ancla no se mira nada más

    score = SCORE_ANCLA
    apoyos = 0
    razones = [t("reason.offplatform_anchor", app=app.group(0))]

    if _cta_re().search(texto):
        score += SCORE_REDIRECCION
        apoyos += 1
        razones.append(t("reason.offplatform_redirect"))
    if _gancho_re().search(texto) or len(_CORAZONES_RE.findall(texto)) >= 2:
        score += SCORE_GANCHO
        apoyos += 1
        razones.append(t("reason.offplatform_hook"))
    if _numero_nuevo_re().search(texto):
        score += SCORE_NUMERO_NUEVO
        apoyos += 1
        razones.append(t("reason.offplatform_new_number"))

    if apoyos == 0:
        # «Mi whatsapp es 600123456» y poco más. Es el mensaje legítimo que más se
        # parece a este spam, así que aquí se para: falsos positivos > falsos negativos.
        return Hit.none()

    if is_first_msg:
        score += SCORE_PRIMER_MENSAJE

    return Hit(
        rule="offplatform_contact",
        score=score,
        reason=" | ".join(razones),
        payload={"app": app.group(0), "signals": apoyos, "first_msg": is_first_msg},
    )
