"""Anuncio porno con enlace a una web (`link_target.check_anuncio`, regla `adult_link`).

Caso real (20-oct-2026, Windows 11): «Elxufas», en el grupo desde 2025 y con
confianza 64, publicó tres anuncios porno con `http://nsfwlook.online`. Solo saltó
`learned_similarity` (50) y la confianza lo anuló: el admin lo tuvo que banear a mano.
"""
from __future__ import annotations

from types import SimpleNamespace

from telegram import MessageEntity

from src.detectors import link_target

ANUNCIO = ("🥵 LOOKING FOR SOMETHING TO JERK OFF TO?🔞\n\nCome join us and jerk off to the "
           "very best leaked content on Telegram.\n\nBeautiful girls, footage from house "
           "parties, amateur home videos, and much more 🐰\n\nTrueXXX❤️\n\n"
           "http://nsfwlook.online\n\nJump into the channel and cum 💦")
CORTO = "Watch Hot Vids 🔞👇🏻\n\nhttp://nsfwlook.online"


def _msg(texto):
    ents = []
    i = texto.find("http")
    if i >= 0:
        fin = texto.find("\n", i)
        fin = len(texto) if fin < 0 else fin
        off = len(texto[:i].encode("utf-16-le")) // 2
        lon = len(texto[i:fin].encode("utf-16-le")) // 2
        ents.append(MessageEntity(type=MessageEntity.URL, offset=off, length=lon))
    return SimpleNamespace(text=texto, caption=None, entities=ents, caption_entities=[])


def test_los_dos_anuncios_reales_caen():
    for texto in (ANUNCIO, CORTO):
        hit = link_target.check_anuncio(_msg(texto))
        assert hit.rule == "adult_link" and hit.score >= 100, texto[:40]
        assert hit.payload["hosts"] == ["nsfwlook.online"]


def test_sin_enlace_no_es_anuncio():
    texto = ANUNCIO.replace("http://nsfwlook.online", "")
    assert not link_target.check_anuncio(_msg(texto))


def test_hablar_de_bloquear_porno_no_dispara():
    """Las palabras de tema no están en la lista, y una web que se llama así no
    basta sin vocabulario explícito en el mensaje."""
    for texto in ("¿Cómo bloqueo el porno y el contenido xxx en el router? Mirad https://pornhub.com",
                  "Con NextDNS bloqueo https://xvideos.com y similares para los críos",
                  "Esta guía para quitar el filtro NSFW va bien: https://example.com/guia"):
        assert not link_target.check_anuncio(_msg(texto)), texto


def test_una_sola_palabra_con_una_web_normal_no_basta():
    assert not link_target.check_anuncio(_msg("Vaya tetas de gráfica 😂 https://www.pccomponentes.com/rtx"))
    assert not link_target.check_anuncio(_msg("Se graduó summa cum laude, mirad https://example.com"))


def test_una_palabra_y_una_web_que_se_anuncia_si():
    assert link_target.check_anuncio(_msg("Chicas calientes aquí https://hotnudes.top"))


def test_el_dominio_dentro_del_texto_no_cuenta_dos_veces():
    """`nudes` va en la lista de palabras y en la de webs: la URL se quita del texto
    antes de contar, así que la web no se cuenta como palabra."""
    assert not link_target.check_anuncio(_msg("Mira esto https://nudes.example.com"))


def test_es_regla_dura_reportable_y_de_contenido():
    from src import autoaprendizaje, handlers
    assert "adult_link" in handlers.HARD_RULES_BAN
    assert "adult_link" in handlers._REPORTABLE_RULES
    assert "adult_link" in autoaprendizaje._REGLAS_DE_CONTENIDO


def test_el_vocabulario_del_control_parental_no_cuenta():
    for texto in ("Para bloquear contenido para adultos y +18 content uso https://pornhub.com en la lista",
                  "El firewall deja el contenido filtrado y los vídeos porno fuera: https://nsfw-filter.io",
                  "Bloquea sexo explícito con https://xxx-blocker.example"):
        assert not link_target.check_anuncio(_msg(texto)), texto
