"""Detector: los «Posts» del perfil usados como catálogo de servicios ilegales.

Los posts son las historias que la persona deja fijadas en su perfil (los lee
`posts_reader`, pie + OCR de la foto). Caso real (1-nov-2026, Windows 10):
«𝐙𝐄𝐑𝐎», sin bio ni canal, con quince posts que ofrecían «Recuperación de estafas
de criptomonedas», «La recuperación de dinero es segura», «Vincula WhatsApp a tu
dispositivo y espía» y «Quieres saber si tu pareja te engaña, comunícate con
nosotros». Pasado por los detectores de mensajes, post a post, no puntuaba nada:
cada pie es una frase corta y suelta. Lo que lo delata es el CONJUNTO.

Mismo molde que `investment_scam`: la señal fuerte es la estructura, no el tema, y
ninguna señal decide sola (todas por debajo de `MIN_SCORE`, hay test).

- **Catálogo**: el vocabulario de servicios ilegales (las listas que ya usan
  `bio_spam` y `commercial_ad`) en DOS o más posts distintos. Uno solo es una
  captura o un meme; varios son un negocio.
- **Oferta**: se ofrece a alguien («nuestro servicio», «comunícate con nosotros»,
  «para tu servicio», o la llamada a la acción de `commercial_ad`).
- **Garantía de recuperación** (ancla estructural, no externalizada): prometer
  que el dinero estafado se recupera. Es la firma de la estafa de «recuperación»,
  que se ceba en quien ya fue estafado; nadie legítimo lo garantiza. El trozo del
  ancla no cuenta además como vocabulario (L33).

Lo que NO cuenta como servicio ilegal: «hacker», «hacking» o «hackeo» a secas.
En grupos de informática salen en memes y capturas, y un curso de hacking ético
no es un servicio a terceros (ya lo excluye la lista inglesa de `bio_spam`).
"""
from __future__ import annotations

import re

from ..i18n import t
from . import Hit

SCORE_CATALOGO = 60      # servicios ilegales en ≥2 posts distintos
SCORE_ILEGAL_UNO = 30    # ...en uno solo
SCORE_OFERTA = 40        # se ofrece a alguien
SCORE_GARANTIA = 45      # promete recuperar el dinero estafado
MIN_SCORE = 100

# Prometer que el dinero perdido vuelve. Dos formas: la afirmación («la
# recuperación de dinero es segura», «recuperación del dinero aquí está
# asegurada») y el gancho («¿has perdido dinero…? la recuperación es posible»).
# Siempre con dinero o fondos al lado: «la recuperación de la lesión es posible»
# es una frase normal.
_GARANTIA_RE = re.compile(
    r"recuperaci[oó]n\s+de(?:l)?\s+(?:tu\s+|su\s+)?"
    r"(?:dinero|fondos|inversi[oó]n(?:es)?|criptomonedas?|cripto|activos)"
    r"[\s\S]{0,40}?(?:asegurada|segura|garantizada|100\s*%)"
    r"|(?:garantizamos|aseguramos)\s+(?:la\s+)?recuperaci[oó]n"
    r"|(?:has|haya[ns]?)\s+perdido\s+(?:tu\s+|su\s+)?(?:dinero|fondos|activos|criptomonedas?)"
    r"[\s\S]{0,120}?recupera"
    r"|(?:guaranteed|100\s*%)\s+(?:funds?\s+|money\s+|crypto\s+)?recovery"
    r"|recovery\s+(?:is\s+)?guaranteed"
    r"|(?:have\s+you|did\s+you)\s+lost\s+(?:your\s+)?(?:money|funds|crypto)[\s\S]{0,120}?recover",
    re.IGNORECASE,
)

# Ofrecerse. Estructural: «nuestro servicio» o «comunícate con nosotros» no los
# dice quien enseña sus fotos de las vacaciones.
_OFERTA_RE = re.compile(
    r"(?<!\w)(?:nuestros?\s+servicios?"
    r"|comun[ií]ca(?:te|rse)\s+con\s+nosotros"
    r"|(?:habla|escr[ií]be)(?:nos)?\s+con\s+nosotros"
    r"|(?:a|para)\s+(?:tu|t[uú]|su)\s+(?:entera\s+)?(?:servicio|disposici[oó]n)"
    r"|our\s+services?|contact\s+us|(?:message|dm|text|inbox)\s+me\s+now)(?!\w)",
    re.IGNORECASE,
)

# Lo que no basta para contar un post como servicio ilegal (ver docstring).
_SOLO_TEMA_RE = re.compile(r"hack(?:ing|er|ers|eo|ear|ea|eado|eos)?", re.IGNORECASE)


def _ilegal_en(texto: str) -> str | None:
    """El primer servicio ilegal del texto que no sea solo el tema, o None."""
    from .bio_spam import _illegal_re
    from .commercial_ad import _illegal_services_re
    for rx in (_illegal_re(), _illegal_services_re()):
        for m in rx.finditer(texto):
            trozo = m.group(0).strip()
            if trozo and not _SOLO_TEMA_RE.fullmatch(trozo):
                return trozo
    return None


def _oferta_en(texto: str) -> str | None:
    m = _OFERTA_RE.search(texto)
    if m:
        return m.group(0)
    from .commercial_ad import _cta_re
    m = _cta_re().search(texto)
    return m.group(0) if m else None


def check(textos: list[str] | None) -> Hit:
    """Juzga los posts del perfil. `textos`: uno por post (pie + OCR)."""
    posts = [(x or "").strip() for x in (textos or [])]
    posts = [x for x in posts if len(x) >= 5]
    if not posts:
        return Hit.none()

    con_ilegal: list[str] = []
    oferta = garantia = None
    for texto in posts:
        g = _GARANTIA_RE.search(texto)
        if g and garantia is None:
            garantia = g.group(0)
        # El trozo del ancla no cuenta además como vocabulario: «recuperación de
        # dinero es segura» sería si no garantía y servicio ilegal a la vez.
        resto = _GARANTIA_RE.sub(" ", texto)
        trozo = _ilegal_en(resto)
        if trozo:
            con_ilegal.append(trozo)
        if oferta is None:
            oferta = _oferta_en(texto)

    score = 0
    reasons: list[str] = []
    if len(con_ilegal) >= 2:
        score += SCORE_CATALOGO
        reasons.append(t("reason.posts_catalogo", n=len(con_ilegal)))
    elif con_ilegal:
        score += SCORE_ILEGAL_UNO
        reasons.append(t("reason.posts_ilegal"))
    if oferta:
        score += SCORE_OFERTA
        reasons.append(t("reason.posts_oferta"))
    if garantia:
        score += SCORE_GARANTIA
        reasons.append(t("reason.posts_garantia"))

    if score < MIN_SCORE:
        return Hit.none()
    return Hit(
        rule="posts_spam",
        score=min(score, 200),
        reason=t("reason.posts_spam", details=" + ".join(reasons)),
        payload={
            "score": score, "posts": len(posts), "posts_ilegales": len(con_ilegal),
            "ejemplos": [x[:60] for x in con_ilegal[:3]],
            "oferta": (oferta or "")[:60], "garantia": (garantia or "")[:80],
        },
    )
