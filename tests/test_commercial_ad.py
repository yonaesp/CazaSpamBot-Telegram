"""Tests para detector commercial_ad (anuncio comercial estructurado)."""
from __future__ import annotations

from types import SimpleNamespace

from src.detectors import commercial_ad as det


def _msg(text):
    return SimpleNamespace(text=text, caption=None)


REAL_SPAM = (
    "🚧 ¡Trabaja en Construcción en España! 🇪🇸\n"
    "💶 Sueldo: 2.000€ – 3.700€ al mes\n"
    "📋 Contrato legal y trabajo estable\n"
    "🏗️ Vacantes disponibles\n"
    "📩 ¡Postúlate ahora! Contáctanos de inmediato\n"
    "https://t.me/SomeChannel"
)


def test_real_spam_triggers():
    """El ejemplo real del user dispara."""
    hit = det.check(_msg(REAL_SPAM), is_first_msg=True)
    assert hit is not None
    assert hit.rule == "commercial_ad"
    assert hit.score >= 100  # múltiples señales acumuladas
    assert hit.payload["emoji_lines"] >= 3
    assert hit.payload["has_money"]
    assert hit.payload["has_cta"]
    assert hit.payload["has_work"]
    assert hit.payload["has_tg_link"]


def test_user_talking_about_salary_no_trigger():
    """Usuario normal mencionando su sueldo → NO dispara."""
    hit = det.check(_msg("mi sueldo es de 1800€ al mes, no me llega para nada"), is_first_msg=False)
    assert hit is None or hit.score == 0


def test_user_asking_about_job_no_trigger():
    """Usuario normal preguntando sobre trabajo → NO dispara."""
    hit = det.check(_msg("alguien sabe cuánto cobra un dev junior? he visto ofertas a 2500€"))
    assert hit is None or hit.score == 0


def test_short_msg_no_trigger():
    """Texto muy corto no se evalúa."""
    hit = det.check(_msg("2000€"))
    assert hit is None or hit.score == 0


def test_only_money_no_trigger():
    """Solo cifras de dinero sin estructura no basta."""
    hit = det.check(_msg("creo que cobra entre 2000€ y 3000€ al mes, no estoy seguro"))
    assert hit is None or hit.score == 0


def test_only_tg_link_no_trigger():
    """Un link t.me/ solo no basta (los users comparten links legítimos)."""
    hit = det.check(_msg("mira este grupo está guapo https://t.me/elgrupobueno"))
    assert hit is None or hit.score == 0


def test_multilinea_emojis_money_dispara():
    """Multi-señal: emojis-header + dinero + CTA + work + link."""
    text = (
        "💰 Gana 5000€ al mes desde casa\n"
        "🏠 Trabajo flexible\n"
        "📞 Contáctame para más info\n"
        "💼 Vacantes limitadas\n"
        "https://t.me/algo"
    )
    hit = det.check(_msg(text), is_first_msg=False)
    assert hit is not None
    assert hit.score >= 60


def test_normal_message_with_emojis_no_trigger():
    """Mensaje normal con emojis decorativos pero sin estructura ni money/cta."""
    text = "buenas! 👋 alguien sabe cómo se hace la rutina de Alexa? 🙏 gracias"
    hit = det.check(_msg(text))
    assert hit is None or hit.score == 0


def test_promo_crypto_score_alto():
    """Spam crypto típico también cae."""
    text = (
        "💰 GANANCIAS GARANTIZADAS\n"
        "📈 Inversión cripto 200% rentabilidad\n"
        "📩 Escríbeme ahora\n"
        "https://t.me/cryptochannel"
    )
    hit = det.check(_msg(text), is_first_msg=True)
    assert hit is not None
    assert hit.score >= 60


CARETAKER_SPAM = (
    "¡URGENTE! Busco a una persona responsable para cuidar de mi casa "
    "mientras estaré de viaje durante 2 años.\n\n"
    "Pago hasta 2.800 € al mes por el servicio. No me importa si tienes "
    "familia, también pueden vivir en la casa.🇪🇸\n\n"
    "Solo necesito que cuiden bien de ella y la mantengan limpia y ordenada.\n\n"
    "Escríbeme o contáctame para más detalles."
)


def test_caretaker_spam_dispara():
    """Spam tipo 'cuidar casa 2.800€/mes' debe disparar."""
    hit = det.check(_msg(CARETAKER_SPAM), is_first_msg=True)
    assert hit is not None
    assert hit.rule == "commercial_ad"
    assert hit.score >= 70
    assert hit.payload["has_periodic_money"]
    assert hit.payload["has_domestic"]
    assert hit.payload["has_urgency"]
    assert hit.payload["has_cta"]


def test_periodic_money_alone_no_dispara():
    """Solo 'X€ al mes' sin estructura ni búsqueda: no dispara."""
    hit = det.check(_msg("creo que cobra 2500€ al mes en su trabajo, no estoy seguro"), is_first_msg=False)
    assert hit is None or hit.score == 0


def test_busco_persona_para_alexa_no_dispara():
    """'Busco persona' para algo del grupo NO debe disparar sin otros patrones."""
    hit = det.check(
        _msg("busco a alguien que me ayude a configurar Alexa, pago un café"),
        is_first_msg=False,
    )
    assert hit is None or hit.score < 60


def test_pet_sitter_pregunta_no_dispara():
    """User legítimo preguntando por cuidador de mascota una vez: poca señal."""
    hit = det.check(
        _msg("alguien sabe cuánto cobra un paseador de perros? he visto que pagan 30€"),
        is_first_msg=False,
    )
    assert hit is None or hit.score < 60


def test_only_urgency_no_dispara():
    """¡URGENTE! solo no basta."""
    hit = det.check(_msg("¡URGENTE! Mi alexa no se conecta a la wifi alguien me ayuda?"))
    assert hit is None or hit.score == 0


HACKING_SPAM = (
    "SERVICIOS PROFESIONALES DE HACKING 🔐\n"
    "Servicios ofrecidos:\n"
    "🌟 Extracción de fotos y videos de la galería del teléfono\n"
    "🌟 Acceso a redes sociales (Instagram, TikTok, WhatsApp)\n"
    "🌟 Obtención de información personal de figuras públicas\n"
    "🌟 Recuperación de dinero\n"
    "⚡ Servicios anónimos, rápidos y seguros (sujeto a disponibilidad).\n"
    "⚠️ Solo para clientes serios. 🌎\n"
    "Solo por tiempo limitado ✅️"
)


def test_hacking_spam_dispara():
    """Caso real Win10: anuncio de servicios ilegales de hacking debe disparar."""
    hit = det.check(_msg(HACKING_SPAM), is_first_msg=False)
    assert hit is not None
    assert hit.rule == "commercial_ad"
    assert hit.score >= 60
    assert "servicios ilegales/scam" in hit.reason


def test_hacking_spam_nfd_dispara():
    """Mismo mensaje con acentos en forma NFD (combining) sigue disparando."""
    import unicodedata
    nfd = unicodedata.normalize("NFD", HACKING_SPAM)
    hit = det.check(_msg(nfd), is_first_msg=False)
    assert hit is not None
    assert hit.score >= 60


def test_pregunta_instagram_normal_no_dispara():
    """User legítimo preguntando por acceso a Instagram NO debe disparar (anti-FP)."""
    hit = det.check(
        _msg("alguien sabe por qué no me funciona el acceso a Instagram desde el pc nuevo?"),
        is_first_msg=False,
    )
    assert hit is None or hit.score < 60
