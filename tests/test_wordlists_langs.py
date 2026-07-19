"""Listas negras por idioma: acumulación, retrocompatibilidad y anti falso positivo.

El foco de este archivo es la regla número uno del proyecto: mejor dejar pasar
spam que banear a un legítimo. Los patrones ingleses se prueban contra mensajes
realistas de un grupo de tecnología en inglés que NO deben disparar nada.
"""
from __future__ import annotations

import re
from unittest.mock import Mock

import pytest

from src import wordlists
from src.detectors import bio_spam, commercial_ad


@pytest.fixture(autouse=True)
def _cache_limpia():
    """Los patrones se cachean por (archivo, dir, idiomas): sin esto un test
    contaminaría al siguiente."""
    wordlists.clear_cache()
    yield
    wordlists.clear_cache()


def _msg(text: str) -> Mock:
    m = Mock()
    m.text = text
    m.caption = None
    return m


# ---------- retrocompatibilidad: instalación sin subdirectorios ----------

def test_sin_subdirectorios_se_comporta_igual_que_antes(tmp_path, monkeypatch):
    """Una instalación existente (solo archivos sueltos) no cambia en nada."""
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    (tmp_path / "lista.txt").write_text("# comentario\n\ncasino\nbet\n  forex  \n", encoding="utf-8")
    assert wordlists.load_terms("lista.txt", ["fallback"]) == ["casino", "bet", "forex"]


def test_sin_archivo_ni_subdirectorios_usa_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    assert wordlists.load_terms("no_existe.txt", ["a", "b"]) == ["a", "b"]


def test_archivo_solo_comentarios_cae_a_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    (tmp_path / "vacio.txt").write_text("# nada útil\n\n", encoding="utf-8")
    assert wordlists.load_terms("vacio.txt", ["def"]) == ["def"]


# ---------- acumulación por idioma ----------

def test_acumula_generico_mas_idioma(tmp_path, monkeypatch):
    """El spam llega en cualquier idioma: los patrones se SUMAN, no se sustituyen."""
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    (tmp_path / "l.txt").write_text("casino\n", encoding="utf-8")
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "l.txt").write_text("fixed matches\n", encoding="utf-8")
    assert wordlists.load_terms("l.txt", ["x"], langs=["en"]) == ["casino", "fixed matches"]


def test_acumula_sobre_los_defaults_si_falta_el_generico(tmp_path, monkeypatch):
    """Sin archivo genérico el bot no se queda sin la protección del código."""
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "l.txt").write_text("carding\n", encoding="utf-8")
    assert wordlists.load_terms("l.txt", ["casino"], langs=["en"]) == ["casino", "carding"]


def test_sin_duplicados_ignorando_mayusculas(tmp_path, monkeypatch):
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    (tmp_path / "l.txt").write_text("casino\nforex\n", encoding="utf-8")
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "l.txt").write_text("CASINO\ncarding\nforex\n", encoding="utf-8")
    assert wordlists.load_terms("l.txt", [], langs=["en"]) == ["casino", "forex", "carding"]


def test_idioma_sin_carpeta_no_estorba(tmp_path, monkeypatch):
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    (tmp_path / "l.txt").write_text("casino\n", encoding="utf-8")
    assert wordlists.load_terms("l.txt", [], langs=["fr", "en"]) == ["casino"]


def test_active_langs_incluye_ingles_siempre(monkeypatch):
    """El inglés es la lengua franca del spam: se carga sea cual sea el idioma."""
    monkeypatch.delenv("BLACKLIST_LANGS", raising=False)
    monkeypatch.setattr(wordlists, "current_lang", lambda: "es")
    assert wordlists.active_langs() == ["es", "en"]
    monkeypatch.setattr(wordlists, "current_lang", lambda: "en")
    assert wordlists.active_langs() == ["en"]  # sin duplicar


def test_blacklist_langs_permite_forzar_idiomas(monkeypatch):
    monkeypatch.setenv("BLACKLIST_LANGS", "es, en ,pt")
    assert wordlists.active_langs() == ["es", "en", "pt"]


# ---------- un regex de usuario no puede tumbar el bot ----------

def test_regex_invalido_se_ignora_y_el_resto_funciona(caplog):
    """Antes, un paréntesis sin cerrar reventaba el import del detector y el bot
    ni arrancaba. Ahora se descarta ese patrón y los demás siguen protegiendo."""
    with caplog.at_level("WARNING"):
        rx = wordlists.compile_alternation(["casino", "(sin cerrar", "forex"])
    assert rx.search("juega al casino")
    assert rx.search("señales de forex")
    assert not rx.search("un mensaje normal")
    assert "inválido" in caplog.text


def test_varios_regex_invalidos_no_dejan_la_lista_inservible():
    rx = wordlists.compile_alternation(["*malo", "casino", "[sin-cerrar", "+otro"])
    assert rx.search("bienvenido al casino")


def test_todos_invalidos_no_casa_nada_y_no_lanza():
    rx = wordlists.compile_alternation(["*malo", "[roto"])
    assert not rx.search("cualquier cosa")


def test_carga_completa_con_archivo_corrupto_no_lanza(tmp_path, monkeypatch):
    """El detector debe poder cargar su lista aunque el usuario la haya roto."""
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    (tmp_path / "l.txt").write_text("casino\n(roto\n", encoding="utf-8")
    rx = wordlists.load_and_compile("l.txt", ["fallback"])
    assert rx.search("el casino de la esquina")


def test_backreference_no_rompe_la_alternancia():
    """Un patrón que compila suelto pero rompe la alternancia (\\1 apuntando a un
    grupo de otro término) se descarta sin llevarse por delante a los demás."""
    rx = wordlists.compile_alternation([r"(?:a)\1", "casino"])
    assert rx.search("vamos al casino")


def test_patrones_del_repo_compilan_todos():
    """Las listas que se versionan en el repo no pueden tener patrones muertos."""
    for archivo in sorted(wordlists._BLACKLIST_DIR.rglob("*.txt")):
        for term in wordlists._read_terms_file(archivo) or []:
            re.compile(term, re.IGNORECASE)  # no debe lanzar


def test_patrones_del_repo_no_empiezan_por_simbolo():
    """`compile_alternation` envuelve en \\b(?:...)\\b y \\b nunca casa delante de
    un símbolo: un patrón que empiece por $ o % estaría muerto en silencio."""
    for archivo in sorted(wordlists._BLACKLIST_DIR.rglob("*.txt")):
        for term in wordlists._read_terms_file(archivo) or []:
            primero = term.replace("(?:", "").replace("(", "").lstrip("\\")[:1]
            assert primero not in "$%+/.@", f"{archivo.name}: {term!r} no casaría nunca"


# ---------- detección real de spam en inglés ----------

SPAM_ANUNCIOS_EN = [
    "🚀 REMOTE JOB OPPORTUNITY AVAILABLE 🚀\n"
    "💰 Make $500 a day working from home\n"
    "📋 No experience required\n"
    "📩 DM me for details https://t.me/+abc123",
    "💵 Now hiring! Weekly payouts guaranteed\n"
    "🔥 Passive income straight from your phone\n"
    "✅ Apply now https://jobs-example-scam.com",
    "PROFESSIONAL HACKING SERVICES\n"
    "We recover lost crypto and stolen funds.\n"
    "We can hack any instagram account. Serious clients only.\n"
    "Contact us on whatsapp",
    "Do you want to change school grades? We erase criminal records and "
    "offer a phone monitoring service. Anonymous services, contact me on telegram",
]


@pytest.mark.parametrize("texto", SPAM_ANUNCIOS_EN)
def test_anuncio_spam_en_ingles_se_detecta(texto):
    hit = commercial_ad.check(_msg(texto), is_first_msg=True)
    assert hit.rule == "commercial_ad", f"no detectado: {texto[:60]!r}"


SPAM_BIOS_EN = [
    "Hot girl 😈🔥 exclusive content, link in my bio https://t.me/+xyz789",
    "Crypto recovery expert 💰 We recover lost funds and stolen bitcoin. "
    "DM me for details https://t.me/+recoveryguy",
    "Private videos 🥵 adults only, hit me up https://t.me/+privatestuff",
]


@pytest.mark.parametrize("bio", SPAM_BIOS_EN)
def test_bio_spam_en_ingles_se_detecta(bio):
    assert bio_spam.check(bio).rule == "bio_spam", f"no detectada: {bio[:60]!r}"


# ---------- ANTI FALSO POSITIVO (lo importante) ----------

HAM_GRUPO_TECH_EN = [
    # busca trabajo de forma normal, sin enlace ni estructura de anuncio
    "Hey everyone, I'm looking for a job as a backend developer. Any "
    "recommendations for companies hiring in Madrid? I have 5 years of experience.",
    # habla de dinero: lo que PAGA, no lo que ofrece
    "I paid 200 a month for that VPS and honestly it was not worth it, I moved "
    "to Hetzner and now I pay way less. Here is my setup: https://github.com/me/dotfiles",
    # "clicked the link" en una consulta de soporte
    "Can someone help me? I clicked the link in that email and now Windows "
    "Defender is complaining about a trojan. Should I run a full scan?",
    # menciona salario y comparte un enlace legítimo
    "The salary range in this offer looks fine to me, but check the reviews on "
    "Glassdoor before you apply. https://glassdoor.com/example",
    # "free", "make money", "win": palabras sueltas que NO pueden banear
    "Free tip: if you want to make money with your old laptop, just sell it on "
    "eBay instead of letting it rot in a drawer. Works every time.",
    # seguridad ofensiva legítima, el vocabulario más peligroso del detector
    "I've been learning about ethical hacking and bug bounty programs, any good "
    "resources? I'm a security researcher and want to move into pentesting.",
    # sorteo real de la comunidad, con emojis
    "Our community giveaway is live! We are giving away 3 licenses. Just react "
    "to this message with 🎉 and I'll pick the winners tomorrow at 8pm.",
    # anuncio de evento con "register now" y enlace: descartado a propósito
    "Register now for the free webinar about Home Assistant automations, it's "
    "this Thursday at 19:00 https://example.com/webinar - see you there!",
    # "bet" como muletilla y "free" comercial legítimo
    "Bet you didn't know that you can use PowerToys to remap keys. It's free "
    "from Microsoft and it saved me so much time on my new keyboard setup.",
    # cripto en conversación normal
    "Does anyone know how much crypto mining costs in electricity these days? "
    "I heard bitcoin is not profitable anymore with these prices.",
    # venta de segunda mano entre miembros, con precio y contacto
    "Selling my old RTX 3060, works perfectly, no boxes. Asking 180 euros, "
    "pickup in Valencia or shipping at cost. Send me a message if interested.",
    # oferta de empleo compartida por un miembro, sin estructura de spam
    "My company is looking for a junior sysadmin, remote friendly. If anyone is "
    "interested I can pass the CV internally, just tell me. No recruiters please.",
]


@pytest.mark.parametrize("texto", HAM_GRUPO_TECH_EN)
def test_mensaje_legitimo_en_ingles_no_dispara(texto):
    hit = commercial_ad.check(_msg(texto), is_first_msg=True)
    assert not hit, f"FALSO POSITIVO ({hit.score}): {hit.reason}"


HAM_BIOS_EN = [
    "Backend developer, security researcher and certified ethical hacker. "
    "I write about pentesting at https://myblog.example.com",
    "Just a guy who loves Windows tweaks and mechanical keyboards. Ask me "
    "anything, hit me up if you need help with drivers.",
    "Freelance designer. Contact me for collaborations. Portfolio: "
    "https://dribbble.com/example",
    "Sysadmin by day, homelab tinkerer by night. Running Home Assistant on a "
    "mini PC. Ask me about Docker.",
]


@pytest.mark.parametrize("bio", HAM_BIOS_EN)
def test_bio_legitima_en_ingles_no_dispara(bio):
    hit = bio_spam.check(bio)
    assert not hit, f"FALSO POSITIVO ({hit.score}): {hit.reason}"


HAM_ESPANOL = [
    # las listas inglesas se cargan TAMBIÉN en grupos españoles: no pueden
    # ensuciar la moderación en castellano
    "Buenas, alguien sabe si merece la pena el pack de Alexa con el Echo Dot? "
    "Lo he visto de oferta pero no sé si esperar al Black Friday.",
    "He actualizado a Windows 11 y el driver de la gráfica va fatal, he probado "
    "a reinstalarlo desde la web de NVIDIA https://nvidia.com/drivers y nada.",
    "Yo pago 12 euros al mes por el hosting y la verdad es que va muy bien, "
    "aquí está la comparativa que hice https://ejemplo.com/comparativa",
]


@pytest.mark.parametrize("texto", HAM_ESPANOL)
def test_las_listas_inglesas_no_afectan_a_mensajes_espanoles(texto):
    hit = commercial_ad.check(_msg(texto), is_first_msg=True)
    assert not hit, f"FALSO POSITIVO ({hit.score}): {hit.reason}"
