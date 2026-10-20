"""Detector: el enlace lleva a un chat que se anuncia solo como spam.

Compañero de `link_reader`, que es quien va a mirar el destino. Aquí solo se juzga
lo que ese destino dice DE SÍ MISMO: su título y su descripción públicas.

Por qué esto no es «otro detector de palabras»:

- No mira el mensaje del usuario. Mira la ficha del chat enlazado, escrita por
  quien monta el canal para atraer clientes. Nadie describe su canal como «packs
  caseros» sin dedicarse a eso.
- Por eso el listón de falsos positivos es distinto al de un mensaje suelto: en un
  grupo de informática o domótica se habla de dinero, de trabajo y de fotos a
  todas horas, pero NADIE enlaza un canal titulado «Jovencitas / Colegialas».

Se acumulan dos listas, ambas editables:

- `config/blacklist/link_target_keywords.txt` — específica de destinos enlazados.
- `config/blacklist/personal_channel_keywords.txt` — el vocabulario de blanqueo,
  apuestas, documentos falsos y accesos robados que ya se usa para el canal del
  perfil. El criterio es idéntico («lo que ningún chat honesto pone en su título»),
  así que se reutiliza en vez de duplicarlo: un término añadido allí protege aquí.

Nota de compilación: igual que en `personal_channel`, se compila SIN el envoltorio
`\\b(?:...)\\b`, porque el chino y el japonés no separan palabras con espacios y el
`\\b` dejaría muertos todos sus patrones. Los patrones latinos traen sus propios `\\b`.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from ..i18n import t
from ..wordlists import compile_alternation, load_and_compile, load_terms
from . import Hit
from .personal_channel import _DEFAULT_CHANNEL_KEYWORDS
from .url_blocklist import _iter_urls

# Alto a propósito: sumado a los 50 del enlace externo pasa de BAN_SCORE. El
# destino confeso es la prueba, no un indicio más.
SCORE = 100

_DEFAULT_LINK_TARGET_KEYWORDS = [
    # --- Venta de contenido sexual (el caso real que originó el detector) ---
    # Los pares van con separador flexible porque estos canales encadenan reclamos
    # con barras: «Mujeres / Packs / Caseros / Videos / Erome / Jovencitas».
    r"\bpacks?\b[\s/|,·+-]{0,3}\b(?:caseros?|exclusivos?|filtrados?|premium)\b",
    r"\b(?:caseros?|exclusivos?|filtrados?)\b[\s/|,·+-]{0,3}\bpacks?\b",
    r"\bpacks?\s+(?:y\s+)?(?:videos?|fotos?)\s+exclusivos?\b",
    r"\b(?:vendo|venta\s+de)\s+packs?\b",
    r"\bjovencitas\b", r"\bcolegialas\b",
    r"\bcontenido\s*\+?\s*18\b", r"\bpack\s+de\s+(?:chicas|nenas|pibas)\b",
    r"\bvideos?\s+porno\b", r"\bporno\s+(?:gratis|amateur|casero)\b",
    r"\bnudes?\s+(?:leaks?|packs?|gratis)\b", r"\bleaks?\s+nudes?\b",
    # «Caseros» emparejado con su reclamo (1-oct-2026, «Caseros Wild»). Suelto no:
    # «remedios caseros».
    r"\bcaseros?\b[\s/|,·+-]{0,3}\b(?:exclusivos?|filtrados?|wild|xxx|hot|calientes?|amateur|leaks?)\b",
    r"\b(?:exclusivos?|filtrados?|xxx|hot|calientes?)\b[\s/|,·+-]{0,3}\bcaseros?\b",
    # --- Reclamo de canal de spam genérico ---
    r"\bcuentas\s+(?:premium|hackeadas)\s+gratis\b",
    r"\btarjetas\s+(?:clonadas|robadas)\b",
]


# --- El anuncio porno con enlace a una web (`adult_link`) ----------------------
# Caso real (20-oct-2026, Windows 11): «Elxufas», en el grupo desde 2025 y con
# confianza 64 (cuenta robada, casi seguro), publicó tres veces «LOOKING FOR
# SOMETHING TO JERK OFF TO?🔞 … leaked content … http://nsfwlook.online». Solo saltó
# `learned_similarity` (50) y la confianza lo dejó en nada. Un enlace web no se
# puede leer como un t.me (y salir a internet a mirarlo delataría al servidor), pero
# aquí el destino también se presenta solo: el NOMBRE de la web y el propio anuncio.
#
# Regla dura, como `link_target_spam`, porque lo que la confianza tiene que proteger
# es a quien comparte algo dudoso, no a una cuenta veterana robada publicando porno.
# Por eso exige mucho: un enlace Y dos señales explícitas DISTINTAS, o una y una web
# que ya se anuncia por el nombre. Las palabras de tema («porno», «xxx», «sexo») NO
# están en la lista, ni lo que se dice al hablar de control parental («contenido
# para adultos», «+18», «sexo explícito», «contenido filtrado» es además lo que
# para un cortafuegos): «cómo bloqueo el porno en el router» es una pregunta normal.
# Medido sobre 453 mensajes legítimos de los cuatro grupos: ni una sola coincidencia
# de vocabulario; caza los tres mensajes del caso.
SCORE_ANUNCIO = 100

_DEFAULT_ADULT_EXPLICIT = [
    r"jerk(?:ing)?\s+off", r"cum(?:ming|shots?)?(?!\s+laude)", r"horny",
    r"puss(?:y|ies)", r"tits", r"boobs", r"blow\s?jobs?", r"masturbat\w*", r"nudes",
    r"(?:leaked|hot|amateur|homemade)\s+(?:vids|videos?|content|pics|photos|tapes?|girls)",
    r"onlyfans\s+(?:leaks?|free|gratis)",
    r"hacerse\s+(?:una\s+)?pajas?", r"pajear\w*", r"foll(?:ar|ando|ada)", r"tetas",
    r"masturb\w+", r"cachond[ao]s?", r"desnudas",
    r"(?:chicas|mujeres|v[ií]deos?|fotos?)\s+(?:calientes|desnudas|hot)",
    r"contenido\s+caliente", r"sexo\s+(?:gratis|en\s+vivo|casual)", r"putas",
]
# Trozos que delatan una web porno en su propio nombre (`nsfwlook.online`).
_DEFAULT_ADULT_DOMAINS = [
    "porn", "nsfw", "xxx", "hentai", "nude", "xvideo", "xnxx", "erome", "fapello",
    "onlyfans", "xhamster", "chaturbate", "stripchat", "bongacams",
]
_EMOJI_18 = "\U0001F51E"  # 🔞: va aparte porque no es letra y el envoltorio no lo casaría
_URL_EN_TEXTO_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def _adult_explicit_re():
    return load_and_compile("adult_explicit.txt", _DEFAULT_ADULT_EXPLICIT)


def _adult_domains_re():
    return compile_alternation(
        load_terms("adult_domains.txt", _DEFAULT_ADULT_DOMAINS), boundaries=False)


def _host(url: str) -> str:
    url = url if "://" in url else "https://" + url
    try:
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def check_anuncio(msg, texto: str | None = None) -> Hit:
    """Anuncio porno con enlace. `texto` es el ya desofuscado; los enlaces salen de
    las entidades del mensaje ORIGINAL, que son las que no se pueden descuadrar."""
    original = (getattr(msg, "text", None) or getattr(msg, "caption", None) or "")
    texto = unicodedata.normalize("NFKC", texto if texto is not None else original)
    urls = list(_iter_urls(msg)) + _URL_EN_TEXTO_RE.findall(original)
    if not urls:
        return Hit.none()
    hosts = sorted({h for h in (_host(u) for u in urls) if h})
    sin_urls = texto
    for u in urls:
        sin_urls = sin_urls.replace(u, " ")
    señales = {re.sub(r"\s+", " ", m.group(0).lower())
               for m in _adult_explicit_re().finditer(sin_urls)}
    if _EMOJI_18 in texto:
        señales.add(_EMOJI_18)
    web_confesa = [h for h in hosts if _adult_domains_re().search(h)]
    if not (len(señales) >= 2 or (señales and web_confesa)):
        return Hit.none()
    return Hit(
        rule="adult_link",
        score=SCORE_ANUNCIO,
        reason=t("reason.adult_link", hosts=", ".join(hosts[:3]) or "?"),
        payload={"hosts": hosts[:5], "señales": sorted(señales)[:8],
                 "web_confesa": web_confesa[:3]},
    )


def _keywords_re():
    terms = load_terms("link_target_keywords.txt", _DEFAULT_LINK_TARGET_KEYWORDS)
    terms += load_terms("personal_channel_keywords.txt", _DEFAULT_CHANNEL_KEYWORDS)
    return compile_alternation(terms, boundaries=False)


def check(destino) -> Hit:
    """Juzga un `link_reader.Destino`. Sin destino legible no dispara."""
    if destino is None:
        return Hit.none()
    texto = getattr(destino, "texto", "") or ""
    if not texto.strip():
        return Hit.none()
    if not _keywords_re().search(texto):
        return Hit.none()
    titulo = (getattr(destino, "titulo", "") or texto)[:80]
    return Hit(
        rule="link_target_spam",
        score=SCORE,
        reason=t("reason.link_target_spam", title=titulo),
        payload={
            "url": getattr(destino, "url", None),
            "title": getattr(destino, "titulo", "")[:200],
            "about": getattr(destino, "descripcion", "")[:200],
        },
    )
