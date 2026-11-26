"""No tener @ ni foto no hace sospechoso a quien manda un adjunto como primer mensaje (L67).

Caso real (24-nov-2026, Windows 11): una cuenta llamada «A», sin @usuario ni foto,
entró el 20-nov y su primer mensaje fue un meme de un USB («tienes que intentarlo 3
veces antes de enchufarlo bien»). `first_msg_media` dio 70 + 20 (sin pie) + 50 (cuenta
sospechosa: sin username, sin foto) = 140: ban en los cuatro grupos. El admin: «no
parece nada ilegítimo, quizás quería caer bien».

Medido sobre todo `moderation_log`: la regla sola, con el perfil sospechoso solo por no
tener @ o foto, baneó 5 veces y 2 eran gente normal (este y uno desbaneado en agosto).
"""
from __future__ import annotations

import ast
import asyncio
import datetime as dt
from pathlib import Path
from types import SimpleNamespace as NS

from src import handlers, i18n, user_signals, verification
from src.detectors import first_msg_media as media_det

RAIZ = Path(__file__).resolve().parent.parent


def _sig(fotos: int = 0, dias: int | None = None):
    antigua = (dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(days=dias)) if dias is not None else None
    return user_signals.UserSignals(user_id=1, photo_count=fotos, oldest_photo=antigua)


def _foto_sin_pie():
    return NS(photo=[NS(file_id="f")], video=None, animation=None, sticker=None, document=None,
              video_note=None, caption=None, text=None, entities=None, caption_entities=None,
              forward_origin=None, reply_markup=None, via_bot=None)


# ------------------------------------------------------------------ el caso

def test_el_meme_del_usb_no_se_banea(monkeypatch):
    """Del perfil al perdón, con las piezas de verdad: sin @, sin foto y nombre «A»."""
    sospechoso, motivos = verification.sospecha_para_adjunto(_sig(fotos=0), None, "A")
    assert (sospechoso, motivos) == (False, [])
    msg = _foto_sin_pie()
    hit = media_det.check(msg, is_first_msg=True, is_suspicious=sospechoso,
                          suspicious_reasons=verification.render_reason_list(motivos))
    assert hit.score == 90                                   # antes, 140: ban

    async def _ocr_limpio(*a, **kw):
        return []
    monkeypatch.setattr(handlers, "_hits_de_la_imagen", _ocr_limpio)
    motivo = asyncio.run(handlers._perdon_por_contenido_limpio(
        None, None, NS(), msg, msg, NS(id=1), [hit]))
    assert motivo == i18n.t("reason.solo_adjunto")


def test_la_verificacion_sigue_viendolo_como_antes():
    """Solo cambia el adjunto: el aviso de sospechosos al entrar no se toca."""
    sospechoso, motivos = verification._is_suspicious_profile(_sig(fotos=0), None, "A")
    assert sospechoso
    assert {m[0] for m in motivos} == {verification.REASON_NO_USERNAME, verification.REASON_NO_PHOTO}


def test_sin_foto_pero_con_arroba_tampoco():
    assert verification.sospecha_para_adjunto(_sig(fotos=0), "berlin", "Ana") == (False, [])


# ------------------------------------------------------------------ lo que sigue contando

def test_el_nombre_en_otro_alfabeto_sigue_siendo_sospechoso():
    sospechoso, motivos = verification.sospecha_para_adjunto(_sig(fotos=0), None, "Мария Иванова")
    assert sospechoso
    assert [m[0] for m in motivos] == [verification.REASON_NON_LATIN_NAME]


def test_la_cuenta_reciente_sigue_siendo_sospechosa():
    sospechoso, motivos = verification.sospecha_para_adjunto(_sig(fotos=1, dias=10), "ana_r", "Ana")
    assert sospechoso
    assert [m[0] for m in motivos] == [verification.REASON_RECENT_ACCOUNT]


def test_con_la_sospecha_de_verdad_sigue_el_ban():
    sospechoso, motivos = verification.sospecha_para_adjunto(_sig(fotos=0), None, "Мария")
    hit = media_det.check(_foto_sin_pie(), is_first_msg=True, is_suspicious=sospechoso,
                          suspicious_reasons=verification.render_reason_list(motivos))
    assert hit.score == 140


# ------------------------------------------------------------------ que no vuelva

def test_el_adjunto_usa_la_sospecha_sin_lo_discreto():
    """`on_message` no llama a `_is_suspicious_profile`: el adjunto pasa por la versión sin @ ni foto."""
    arbol = ast.parse((RAIZ / "src" / "handlers.py").read_text(encoding="utf-8"))
    llamadas = [n.func.attr for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "verification"]
    assert "sospecha_para_adjunto" in llamadas
    assert "_is_suspicious_profile" not in llamadas
