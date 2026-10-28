"""Tests para detector bio_spam."""
from __future__ import annotations

from src.detectors import bio_spam as det


CASE_REAL = "Hier geht's zu mir😈:https://t.me/+Th8CEkvfiWw0ODNk 🔥🥵"


def test_caso_real_aleman_invite_emojis_dispara():
    hit = det.check(CASE_REAL)
    assert hit is not None
    assert hit.rule == "bio_spam"
    assert hit.score >= 60


def test_bio_normal_no_dispara():
    assert det.check("Hola, soy Juan de Madrid. Me gusta la tecnología.") is None or det.check("Hola, soy Juan").score == 0


def test_bio_vacia_no_dispara():
    assert det.check(None) is None or det.check(None).score == 0
    assert det.check("").score == 0 if det.check("") else True


def test_bio_solo_link_no_invite():
    hit = det.check("Mira mi canal: https://t.me/elgrupobueno")
    # solo link t.me no invite + sin más señales = 25 pts no dispara
    assert hit is None or hit.score == 0


def test_bio_invite_solo_no_dispara():
    """Solo el invite link (35 pts) sin más señales no llega a 60."""
    hit = det.check("Únete: https://t.me/+abc123XYZ")
    assert hit is None or hit.score == 0


def test_onlyfans_keyword_dispara():
    """Keyword onlyfans + URL = ban."""
    hit = det.check("Subscribe to my OnlyFans https://onlyfans.com/mia 💋")
    assert hit is not None
    assert hit.score >= 60


def test_crypto_signal_dispara():
    hit = det.check("Crypto trading signals 100% win rate https://t.me/+xyz")
    assert hit is not None


def test_bio_money_cta_idioma_dispara():
    hit = det.check("Hier geht's zu mir, gana 5000€/mes, contáctame ya https://t.me/+xyz")
    assert hit is not None
    assert hit.score >= 60


def test_bio_legitima_con_url_propio_no_dispara():
    """Bio con URL propio (web personal) sin otras señales — score muy bajo."""
    hit = det.check("Soy Marta, mi web: https://martagomez.es")
    assert hit is None or hit.score == 0


def test_bio_corta_no_evalua():
    assert det.check("hi") is None or det.check("hi").score == 0


def test_caso_johanna_aleman_geil():
    """Bio alemán adulto con invite + emojis (caso Johanna 2026-06-03)."""
    hit = det.check("Mehr von der geilen Lea💦: https://t.me/+Th8CEkvfiWw0ODNk 😈")
    assert hit is not None
    assert hit.score >= 60


def test_caso_hacking_bio_web_externa():
    """Bio de servicios de hacking + web externa + CTA (caso CHRIST WHITE HACK 2026-06-07)."""
    bio = (
        "un experto en materia de piratería informática"
        "☆☆https://christwhite.websites.co.in/☆ Puedes consultar el sitio"
    )
    hit = det.check(bio)
    assert hit is not None
    assert hit.rule == "bio_spam"
    assert hit.score >= 60
    assert "hacking" in hit.reason


def test_bio_legit_con_web_no_dispara():
    """Bio normal con web/blog personal NO debe disparar (anti-FP)."""
    for legit in (
        "Me gusta la informática y Alexa. Visita mi blog https://miblog.com",
        "Desarrollador de software. https://github.com/usuario",
        "Aficionado a la ciberseguridad y al hardware",
    ):
        hit = det.check(legit)
        assert hit is None or hit.score < 60, legit


# Caso real (28-oct-2026): Charlotte entró en Windows 10 con esta bio y el bot no
# sumó nada: el enlace iba sin `https://` y «stake» no estaba en la lista.
CHARLOTTE = "Reels are ready when you are — stake1036.com/?c=tg"


def test_charlotte_espejo_de_casino_con_campana_dispara():
    hit = det.check(CHARLOTTE)
    assert hit.rule == "bio_spam" and hit.score >= 60


def test_dominio_sin_esquema_con_ruta_cuenta_como_enlace():
    assert det._BARE_URL_RE.search("mira stake1036.com/?c=tg")
    assert det._BARE_URL_RE.search("github.com/juan")


def test_dominio_sin_ruta_o_correo_no_es_enlace():
    assert not det._BARE_URL_RE.search("Ingeniero, trabajo en Google.com")
    assert not det._BARE_URL_RE.search("escríbeme a juan@gmail.com/")


def test_enlace_con_campana_y_llamada_a_la_accion_no_basta():
    """Una tienda con ?ref= y «click here» se queda en 50: hace falta el tema."""
    assert det.check("Mi tienda: tienda.com/?ref=tg click here").score == 0


def test_stake_como_palabra_inglesa_no_dispara():
    assert det.check("Everything is at stake. Stakeholder at ACME").score == 0
    assert det.check("stake.com").score == 0


def test_web_personal_sin_campana_no_dispara():
    assert det.check("github.com/juanperez · Windows y Linux").score == 0
