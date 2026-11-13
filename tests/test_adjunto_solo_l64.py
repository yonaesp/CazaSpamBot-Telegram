"""Un adjunto en el primer mensaje no castiga solo si el perfil no es sospechoso (L64).

Caso real (13-nov-2026, Windows 11): «Javier» (784909, una cuenta de 2013 con foto
y @) entró el 30-sep, no escribió en 44 días y su primer mensaje fue un sticker
animado. `first_msg_media` dio 70 + 20 (sin pie) = 90, por encima del umbral de
expulsión, con `is_suspicious: false` en su propio payload: expulsado, y el aviso
decía «una foto o vídeo, con un perfil sospechoso».

Medido sobre todo `moderation_log`: como regla única y con el perfil normal había
expulsado 3 veces (una foto, un vídeo y este sticker) y las 3 eran gente legítima;
con el perfil sospechoso, 4 de sus 5 bans siguen en pie.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace as NS

import pytest

from src import handlers, i18n
from src.detectors import Hit
from src.detectors import first_msg_media as media_det


def _hit(rule: str, score: int, **payload) -> Hit:
    return Hit(rule=rule, score=score, reason=rule, payload=payload or None)


def _msg(**kw):
    base = dict(photo=None, video=None, animation=None, sticker=None, document=None,
                video_note=None, caption=None, text=None, entities=None,
                caption_entities=None, forward_origin=None, reply_markup=None, via_bot=None)
    base.update(kw)
    return NS(**base)


STICKER = NS(set_name="Minions", emoji="😍", is_animated=True)
ADJUNTO_SOLO = [_hit("first_msg_media", 90, media_type="sticker", caption_len=0, is_suspicious=False)]


def _perdon(real, msg, monkeypatch, hits_imagen=()):
    async def _falso(*a, **kw):
        return list(hits_imagen)
    monkeypatch.setattr(handlers, "_hits_de_la_imagen", _falso)
    return asyncio.run(handlers._perdon_por_contenido_limpio(
        None, None, NS(), msg, msg, NS(id=784909), real))


# ------------------------------------------------------------------ el caso

def test_el_sticker_de_javier_no_se_castiga(monkeypatch):
    """Del detector al perdón, con el hit de verdad: el payload es el contrato entre los dos."""
    msg = _msg(sticker=STICKER)
    hit = media_det.check(msg, is_first_msg=True, is_suspicious=False, suspicious_reasons=[])
    assert hit.rule == "first_msg_media" and hit.score == 90      # por encima de KICK_SCORE (70)
    motivo = _perdon([hit], msg, monkeypatch)
    assert motivo == i18n.t("reason.solo_adjunto")


@pytest.mark.parametrize("campo", ["photo", "video", "animation", "document", "video_note"])
def test_vale_para_cualquier_adjunto(campo, monkeypatch):
    """Los otros dos expulsados de la medida mandaron una foto y un vídeo."""
    assert _perdon(ADJUNTO_SOLO, _msg(**{campo: [object()] if campo == "photo" else NS(mime_type="x/y")}),
                   monkeypatch)


def test_con_un_pie_corto_y_limpio_tambien(monkeypatch):
    """«Me sale este error» con una captura no llega a los 40 caracteres del otro perdón."""
    assert _perdon(ADJUNTO_SOLO, _msg(photo=[object()], caption="Me sale este error, alguna idea?"),
                   monkeypatch)


# ------------------------------------------- lo que tiene que seguir cayendo

def test_con_el_perfil_sospechoso_se_castiga_como_siempre(monkeypatch):
    msg = _msg(sticker=STICKER)
    hit = media_det.check(msg, is_first_msg=True, is_suspicious=True, suspicious_reasons=["sin foto"])
    assert hit.score == 140
    assert _perdon([hit], msg, monkeypatch) == ""


def test_sin_saber_si_el_perfil_es_sospechoso_no_se_perdona(monkeypatch):
    """`is_suspicious` tiene que ser False de verdad, no faltar."""
    assert _perdon([_hit("first_msg_media", 90)], _msg(sticker=STICKER), monkeypatch) == ""
    assert _perdon([_hit("first_msg_media", 90, is_suspicious=None)], _msg(sticker=STICKER), monkeypatch) == ""


def test_con_otra_regla_no_se_perdona(monkeypatch):
    """El caso Joka (3-oct-2026): foto a los 6 s de entrar, perfil normal. Sigue baneado."""
    real = [_hit("jfm_fast", 30, delta_s=6), *ADJUNTO_SOLO]
    assert _perdon(real, _msg(photo=[object()]), monkeypatch) == ""
    assert _perdon([*ADJUNTO_SOLO, _hit("commercial_ad", 100)], _msg(photo=[object()]), monkeypatch) == ""


@pytest.mark.parametrize("pie", [
    "mira https://astrurl.io/p", "entra en t.me/loquesea", "info en www.ejemplo.com", "escribe a @canaldeofertas",
])
def test_un_enlace_o_una_mencion_en_el_pie_no_se_perdona(pie, monkeypatch):
    assert _perdon(ADJUNTO_SOLO, _msg(photo=[object()], caption=pie), monkeypatch) == ""


@pytest.mark.parametrize("tipo", ["url", "text_link", "mention", "text_mention"])
def test_un_enlace_escondido_en_las_entidades_tampoco(tipo, monkeypatch):
    """Un `text_link` no se ve en el texto: «pincha aquí» con el enlace por debajo."""
    msg = _msg(photo=[object()], caption="pincha aquí", caption_entities=(NS(type=tipo),))
    assert _perdon(ADJUNTO_SOLO, msg, monkeypatch) == ""
    msg = _msg(sticker=STICKER, entities=[NS(type=tipo)])
    assert _perdon(ADJUNTO_SOLO, msg, monkeypatch) == ""


@pytest.mark.parametrize("campo", ["forward_origin", "reply_markup", "via_bot"])
def test_reenviado_con_botones_o_via_bot_no_se_perdona(campo, monkeypatch):
    """Un reenvío pasados los 3 minutos ya no dispara `forward_first_msg`: se mira aquí."""
    assert _perdon(ADJUNTO_SOLO, _msg(photo=[object()], **{campo: object()}), monkeypatch) == ""


def test_el_cartel_de_spam_sin_pie_no_se_perdona(monkeypatch):
    assert _perdon(ADJUNTO_SOLO, _msg(photo=[object()]), monkeypatch,
                   hits_imagen=[_hit("commercial_ad", 120)]) == ""


def test_si_la_imagen_no_se_puede_leer_no_se_perdona(monkeypatch):
    async def _revienta(*a, **kw):
        raise RuntimeError("Telegram no da el fichero")
    monkeypatch.setattr(handlers, "_hits_de_la_imagen", _revienta)
    assert asyncio.run(handlers._perdon_por_contenido_limpio(
        None, None, NS(), _msg(photo=[object()]), _msg(), NS(id=1), ADJUNTO_SOLO)) == ""


def test_un_sticker_no_paga_el_ocr(monkeypatch):
    async def _no_debe_llamarse(*a, **kw):
        raise AssertionError("se ha leído una imagen que no existe")
    monkeypatch.setattr(handlers, "_hits_de_la_imagen", _no_debe_llamarse)
    msg = _msg(sticker=STICKER)
    assert asyncio.run(handlers._perdon_por_contenido_limpio(
        None, None, NS(), msg, msg, NS(id=1), ADJUNTO_SOLO))


def test_otra_regla_de_forma_sola_sin_texto_sigue_sin_perdon(monkeypatch):
    """La puerta nueva es solo para `first_msg_media`: un reenvío sin texto no entra."""
    real = [_hit("forward_first_msg", 80, origin_type="user", is_suspicious=False)]
    assert _perdon(real, _msg(photo=[object()]), monkeypatch) == ""
    # Ni dos de forma juntas: reenviarse una foto sin escribir nada sigue como estaba.
    assert _perdon([*real, *ADJUNTO_SOLO], _msg(photo=[object()]), monkeypatch) == ""


# ------------------------------------------------------------ traza y textos

def test_la_auditoria_dice_que_sticker_era():
    hit = media_det.check(_msg(sticker=STICKER), is_first_msg=True, is_suspicious=False)
    assert hit.payload["sticker_set"] == "Minions" and hit.payload["sticker_emoji"] == "😍"
    foto = media_det.check(_msg(photo=[object()]), is_first_msg=True, is_suspicious=False)
    assert "sticker_set" not in foto.payload


@pytest.mark.parametrize("lang", ["es", "en"])
def test_la_explicacion_no_habla_solo_de_fotos_y_videos(lang):
    """El aviso de Javier decía «una foto o vídeo» y era un sticker."""
    assert "sticker" in i18n.t("rule.first_msg_media", _lang=lang).lower()
    motivo = i18n.t("reason.solo_adjunto", _lang=lang)
    assert motivo != "reason.solo_adjunto" and "<" not in motivo
