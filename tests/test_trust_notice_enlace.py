"""El aviso por privado lleva enlace al mensaje, y dice la verdad sobre por qué.

Caso real (19-sep-2026, Windows 11): a «Eduardo», **confianza 1/10**, preguntando
por qué su PC no se veía a sí misma en la red local, le llegó al admin un aviso
encabezado «Algo raro de alguien de confianza» y rematado con «su historial le
avala». Ninguna de las dos cosas era cierta: el aviso venía del perdón por señales
de forma (`first_msg_media` en solitario), que se dispara justamente con gente
recién llegada. Y no traía forma de ir al mensaje: había que buscarlo a mano.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src import handlers
from src.i18n import t, set_lang


def _msg(chat_id=-1001190184646, username=None, mid=60588):
    return SimpleNamespace(message_id=mid, chat_id=chat_id,
                           chat=SimpleNamespace(id=chat_id, username=username, title="W11"))


# --- el permalink ------------------------------------------------------------

def test_grupo_publico_usa_su_username():
    """La forma que el propio admin pegó en el chat."""
    assert handlers._enlace_al_mensaje(_msg(username="Windows11ESP")) == \
        "https://t.me/Windows11ESP/60588"


def test_supergrupo_privado_usa_la_forma_c():
    """Se le quita el prefijo `-100` al chat_id, no el signo solo."""
    assert handlers._enlace_al_mensaje(_msg()) == "https://t.me/c/1190184646/60588"


def test_un_grupo_basico_no_tiene_permalink():
    """No existe, así que no se inventa: la línea del enlace desaparece."""
    assert handlers._enlace_al_mensaje(_msg(chat_id=-4512345)) is None
    assert handlers._enlace_al_mensaje(_msg(chat_id=2089088627)) is None   # un DM


def test_sin_message_id_no_se_construye_nada():
    assert handlers._enlace_al_mensaje(_msg(mid=None)) is None
    assert handlers._enlace_al_mensaje(SimpleNamespace(message_id=1, chat=None)) is None


# --- el texto del aviso ------------------------------------------------------

def _render(avala: bool, url: str | None):
    return t("hdl.trust_notice_dm",
             cabecera=t("hdl.tn.head_trusted" if avala else "hdl.tn.head_no_evidence"),
             pie=t("hdl.tn.foot_trusted" if avala else "hdl.tn.foot_no_evidence"),
             enlace=t("hdl.tn.link", url=url) if url else "",
             uid=2089088627, name="Eduardo", trust="🔴 1/10", chat="W11",
             rules="first_msg_media", action="ban", reason="x", text="y")


def test_el_enlace_sale_en_el_aviso():
    for lang in ("es", "en"):
        set_lang(lang)
        txt = _render(True, "https://t.me/Windows11ESP/60588")
        assert 'href="https://t.me/Windows11ESP/60588"' in txt
    set_lang("es")


def test_sin_permalink_no_queda_ni_rastro_de_la_linea():
    """Ni un `<a href="None">` ni un `{enlace}` a medio rellenar."""
    for lang in ("es", "en"):
        set_lang(lang)
        txt = _render(True, None)
        assert "None" not in txt and "{" not in txt and "<a" not in txt
    set_lang("es")


def test_sin_confianza_el_aviso_NO_dice_que_el_historial_avala():
    """El encabezado falso que destapó esto: confianza 1/10 y «de confianza»."""
    for lang in ("es", "en"):
        set_lang(lang)
        txt = _render(False, None).lower()
        for mentira in ("de confianza", "historial", "trusted", "history"):
            assert mentira not in txt, f"[{lang}] sigue diciendo «{mentira}»"
    set_lang("es")


def test_con_confianza_se_conserva_el_texto_de_siempre():
    set_lang("es")
    txt = _render(True, None)
    assert "confianza" in txt.lower() and "historial" in txt.lower()


# --- invariantes -------------------------------------------------------------

def test_los_dos_perdones_sin_historial_lo_declaran():
    """El perdón por forma y el veto del modelo mandan `avala_historial=False`.

    Se cuenta sobre el fuente porque el fallo es invisible: el aviso se manda
    igual, solo que mintiendo. Si aparece un quinto llamador, que se piense a qué
    variante pertenece.
    """
    fuente = Path("src/handlers.py").read_text(encoding="utf-8")
    llamadas = fuente.count("await _send_trust_notice(")
    assert llamadas == 4, f"hay {llamadas} llamadas; revisa la variante de la nueva"
    assert fuente.count("avala_historial=False") == 2


def test_las_claves_nuevas_estan_en_los_dos_idiomas():
    claves = {"hdl.tn.head_trusted", "hdl.tn.head_no_evidence",
              "hdl.tn.foot_trusted", "hdl.tn.foot_no_evidence", "hdl.tn.link"}
    for lang in ("es", "en"):
        d = json.loads(Path(f"src/locales/{lang}.json").read_text(encoding="utf-8"))
        assert claves <= set(d), f"faltan en {lang}: {claves - set(d)}"
