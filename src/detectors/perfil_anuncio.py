"""Detector: el perfil es un anuncio, y dos cosas lo dicen a la vez.

Caso real (19-nov-2026, Domótica): «BEST IPTV RESELLING PANEL 🎁»,
Premium, con la bio «Need a reliable IPTV service or reseller
panel available» y nueve posts con el catálogo. CAS lo tenía con una infracción.
El bot solo preguntó. Cada cosa por separado no llegaba a nada:

- CAS con una sola infracción, por regla, pregunta y no banea.
- La bio no lleva enlace: `bio_spam` le daba 0.
- Los posts le daban 0 a `posts_perfil`: nadie sabía que revender IPTV es un
  servicio ilegal (el vocabulario va en `bio_illegal_services.txt`).
- El nombre no lo juzgaba nadie por lo que dice, solo por su alfabeto.

Decisión del admin ese día: «si ya tiene un cas y todos esos posts debería ser
motivo de ban porque suma dos cosas».

Las «cosas» son los escaparates del perfil que anuncian un servicio (nombre, bio,
posts, canal) y estar en CAS. Mismo molde que `investment_scam`: ninguna decide
sola (hay test). Hay ban en dos casos:

- **CAS + un escaparate.** Dos fuentes que no se conocen: un admin de otro grupo
  lo marcó, y su propio perfil vende algo.
- **El nombre + otro escaparate.** Una persona no se llama como un servicio. Si
  además lo repite la bio, un post o el canal, la cuenta es un cartel.

Lo que NO banea a propósito: bio y posts sin el nombre ni CAS. Un técnico con
«experto en seguridad» en la bio y un post sobre un spyware cumpliría, y es una
persona normal. Eso lo siguen juzgando `bio_spam` y `posts_perfil` con sus
umbrales.

El vocabulario es el de servicios ilegales de `bio_spam` y `commercial_ad`, por
`posts_perfil._ilegal_en`: «hacker» a secas no cuenta, ni «IPTV» a secas.
"""
from __future__ import annotations

import unicodedata

from ..i18n import t
from . import Hit

SCORE_BASE = 100     # las dos cosas mínimas
SCORE_EXTRA = 30     # cada cosa de más
REGLA = "perfil_anuncio"


def nombre_de(first_name: str | None, last_name: str | None = None) -> str:
    """El nombre visible entero, que es lo que se lee en el grupo."""
    return " ".join(x.strip() for x in (first_name, last_name) if x and x.strip())


def _servicio_en(texto: str | None) -> str | None:
    """El servicio que anuncia el texto, o None. NFKC: «𝐈𝐏𝐓𝐕» cuenta como «IPTV»."""
    if not texto or not texto.strip():
        return None
    from .posts_perfil import _ilegal_en
    return _ilegal_en(unicodedata.normalize("NFKC", texto))


def escaparates(nombre: str | None, bio: str | None = None,
                posts: list[str] | None = None, canal: str | None = None) -> dict[str, str]:
    """Qué escaparates del perfil anuncian un servicio, con el trozo que lo dice."""
    from ..wordlists import modo_ocr
    vistos: dict[str, str] = {}
    trozo = _servicio_en(nombre)
    if trozo:
        vistos["nombre"] = trozo
    trozo = _servicio_en(bio)
    if trozo:
        vistos["bio"] = trozo
    # Los posts llevan texto de OCR: se miran con el vocabulario de `ocr/` sumado.
    with modo_ocr():
        for texto in posts or []:
            trozo = _servicio_en(texto)
            if trozo:
                vistos["posts"] = trozo
                break
    trozo = _servicio_en(canal)
    if trozo:
        vistos["canal"] = trozo
    return vistos


def check(nombre: str | None, bio: str | None = None, posts: list[str] | None = None,
          canal: str | None = None, cas: int = 0) -> Hit:
    """Juzga el perfil entero. `cas`: infracciones en CAS (0 si no está o no se sabe)."""
    vistos = escaparates(nombre, bio, posts, canal)
    if not vistos:
        return Hit.none()
    en_cas = int(cas or 0) >= 1
    por_nombre = "nombre" in vistos and len(vistos) >= 2
    if not (en_cas or por_nombre):
        return Hit.none()

    cosas = len(vistos) + (1 if en_cas else 0)
    donde = ", ".join(t(f"perfil_anuncio.{clave}") for clave in vistos)
    servicio = next(iter(vistos.values()))[:60]
    reason = t("reason.perfil_anuncio", servicio=servicio, donde=donde)
    if en_cas:
        reason += " + " + t("reason.perfil_anuncio_cas")
    return Hit(
        rule=REGLA,
        score=min(200, SCORE_BASE + SCORE_EXTRA * (cosas - 2)),
        reason=reason,
        payload={
            "escaparates": list(vistos), "cas": int(cas or 0),
            "ejemplos": {clave: trozo[:60] for clave, trozo in vistos.items()},
        },
    )
