"""Tests del detector `personal_channel`.

El foco está en los ANTI falsos positivos: tener un canal personal enlazado en el
perfil es completamente legítimo, así que la mayoría de estos casos comprueban
que el detector NO dispara.
"""
from __future__ import annotations

import pytest

from src import i18n
from src.detectors import personal_channel as pc

# Título del caso real (2026-07-19): «canal de notificación de liquidación del
# equipo de blanqueo de dinero del Grupo Hengtai».
CANAL_REAL = "恒泰集团招洗钱车队结账通知频道"
# Mismo alfabeto, contenido inocente («mi diario de viajes»): sirve para aislar la
# señal «título en otro alfabeto» de la señal «vocabulario ilícito».
CANAL_CHINO_NEUTRO = "我的旅行日记频道"

ES = ["latin"]           # grupo español: solo alfabeto latino
RU = ["latin", "cyrillic"]  # grupo bilingüe donde el cirílico SÍ está permitido


@pytest.fixture(autouse=True)
def _es():
    """Los motivos vienen de los paquetes de idioma: se fija ES para no depender
    del idioma global que haya dejado otro test."""
    previo = i18n.current_lang()
    i18n.set_lang("es")
    yield
    i18n.set_lang(previo)


# ---------- POSITIVO: el caso real ----------

def test_caso_real_matthew():
    """Nombre latino, sin foto, sin bio, canal en chino. Debe cazarse."""
    hit = pc.check(
        CANAL_REAL, first_name="Matthew", allowed_scripts=ES,
        has_photo=False, has_bio=False,
    )
    assert hit
    assert hit.rule == "personal_channel_spam"
    assert hit.score >= pc.MIN_SCORE
    assert hit.payload["name_mismatch"] is True
    assert hit.payload["dominant_script"] == "han"


def test_caso_real_pondera_la_discordancia_por_encima_de_cada_senal():
    """El plus por «nombre latino + canal en otro alfabeto» debe pesar más que
    cualquiera de las dos señales por separado."""
    assert pc.SCORE_NAME_MISMATCH > pc.SCORE_FOREIGN_TITLE
    solo_ajeno = pc.SCORE_FOREIGN_TITLE
    con_discordancia = pc.SCORE_FOREIGN_TITLE + pc.SCORE_NAME_MISMATCH
    assert con_discordancia > 2 * solo_ajeno - pc.SCORE_FOREIGN_TITLE


def test_ninguna_senal_suelta_llega_a_banear():
    """Contrato del detector: hacen falta al menos dos señales."""
    for peso in (pc.SCORE_FOREIGN_TITLE, pc.SCORE_NAME_MISMATCH,
                 pc.SCORE_KEYWORDS, pc.SCORE_HIDDEN_PROFILE):
        assert peso < pc.MIN_SCORE


def test_titulo_ajeno_sin_vocabulario_ilicito_y_perfil_completo_no_basta():
    """Nombre latino + canal chino de contenido inocente, con foto y bio: queda
    por debajo del umbral. Es justo el caso de un chino que vive aquí y tiene su
    canal personal en su idioma."""
    hit = pc.check(
        CANAL_CHINO_NEUTRO, first_name="Matthew", allowed_scripts=ES,
        has_photo=True, has_bio=True,
    )
    assert not hit


def test_vocabulario_ilicito_pesa_aunque_el_perfil_este_completo():
    """El caso real con foto y bio sigue cayendo: el título lo delata solo."""
    hit = pc.check(
        CANAL_REAL, first_name="Matthew", allowed_scripts=ES,
        has_photo=True, has_bio=True,
    )
    assert hit
    assert hit.payload["keywords"] is True


def test_keywords_ilicitas_en_titulo_latino_con_perfil_vacio():
    hit = pc.check(
        "Money Laundering Crew 2026", first_name="Carlos", allowed_scripts=ES,
        has_photo=False, has_bio=False,
    )
    assert hit
    assert hit.payload["keywords"] is True


def test_keywords_solas_con_perfil_completo_no_disparan():
    """Un título borderline no puede banear por sí solo."""
    assert not pc.check(
        "Money Laundering Crew 2026", first_name="Carlos", allowed_scripts=ES,
        has_photo=True, has_bio=True,
    )


# ---------- ANTI FALSO POSITIVO ----------

def test_espanol_con_canal_de_fotos_de_montana():
    assert not pc.check(
        "Mis fotos de montaña", first_name="Jonatan", last_name="Pradas",
        username="jonatan", allowed_scripts=ES, has_photo=True, has_bio=True,
    )


def test_espanol_con_canal_de_montana_y_perfil_vacio():
    """Aunque no tenga foto ni bio: el título no tiene nada raro."""
    assert not pc.check(
        "Mis fotos de montaña", first_name="Jonatan", allowed_scripts=ES,
        has_photo=False, has_bio=False,
    )


def test_ruso_legitimo_en_grupo_donde_el_cirilico_esta_permitido():
    assert not pc.check(
        "Мои путешествия по России", first_name="Дмитрий", allowed_scripts=RU,
        has_photo=True, has_bio=True,
    )


def test_ruso_legitimo_sin_foto_ni_bio_tampoco_dispara():
    """El cirílico está permitido, así que no hay alfabeto ajeno que contar y el
    perfil vacío por sí solo no llega al umbral."""
    assert not pc.check(
        "Мои путешествия по России", first_name="Дмитрий", allowed_scripts=RU,
        has_photo=False, has_bio=False,
    )


def test_canal_titulado_con_el_propio_nombre():
    assert not pc.check(
        "Canal de Jonatan Pradas", first_name="Jonatan", last_name="Pradas",
        allowed_scripts=ES, has_photo=True, has_bio=True,
    )


def test_sin_canal_personal_el_caso_mayoritario():
    assert not pc.check(None, first_name="Jonatan", allowed_scripts=ES)
    assert not pc.check("", first_name="Jonatan", allowed_scripts=ES)
    assert not pc.check("   ", first_name="Jonatan", allowed_scripts=ES)


def test_canal_en_el_mismo_script_que_el_nombre_y_el_grupo():
    assert not pc.check(
        "Recetas de la abuela", first_name="María", last_name="Gómez",
        allowed_scripts=ES, has_photo=False, has_bio=True,
    )


def test_titulo_con_una_palabra_suelta_en_otro_alfabeto_no_basta():
    """Ratio por debajo del umbral: un guiño en otro alfabeto no es señal."""
    hit = pc.check(
        "Mi canal de anime 日本", first_name="Laura", allowed_scripts=ES,
        has_photo=False, has_bio=False,
    )
    assert not hit


def test_titulo_solo_emojis_y_numeros_no_dispara():
    """Sin letras no hay script dominante que reprochar."""
    assert not pc.check(
        "🔥🔥 2026 🔥🔥", first_name="Laura", allowed_scripts=ES,
        has_photo=False, has_bio=False,
    )


def test_nombre_sin_letras_no_cobra_el_plus_de_discordancia():
    """Llamarse «⭐⭐⭐» no demuestra que te disfraces de local: sin el plus, el
    título ajeno + perfil vacío se queda por debajo del umbral."""
    hit = pc.check(
        CANAL_CHINO_NEUTRO, first_name="⭐⭐⭐", allowed_scripts=ES,
        has_photo=False, has_bio=False,
    )
    assert not hit


def test_nombre_tambien_en_el_alfabeto_ajeno_no_es_disfraz():
    """Nombre chino + canal chino: no hay discordancia. Sigue sin llegar al
    umbral (lo suyo lo mira `obvious_spam_profile`, no este detector)."""
    hit = pc.check(
        CANAL_CHINO_NEUTRO, first_name="李伟", allowed_scripts=ES,
        has_photo=False, has_bio=False,
    )
    assert not hit


# ---------- sin Telethon ----------

def test_sin_telethon_no_hay_titulo_y_no_rompe():
    """Sin señales de perfil, `personal_channel_title` es None: el detector
    devuelve Hit.none() sin tocar nada."""
    hit = pc.check(None, allowed_scripts=ES, has_photo=False, has_bio=False)
    assert not hit
    assert hit.rule == ""
    assert hit.score == 0


def test_defaults_no_exigen_datos_de_perfil():
    """Llamarlo solo con el título (todo lo demás por defecto) no debe lanzar."""
    assert not pc.check("Mis fotos de montaña")


# ---------- lista de keywords editable ----------

def test_keywords_cjk_casan_sin_separadores_de_palabra(tmp_path, monkeypatch):
    """El chino no separa palabras con espacios: si la lista se compilara con
    \\b(?:...)\\b, TODOS los patrones CJK quedarían muertos sin avisar."""
    from src import wordlists

    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    (tmp_path / "personal_channel_keywords.txt").write_text("洗钱\n", encoding="utf-8")
    wordlists.clear_cache()
    try:
        assert pc._keywords_re().search(CANAL_REAL)
    finally:
        wordlists.clear_cache()


def test_el_enganche_del_join_cuadra_con_la_firma_del_detector():
    """Guarda anti-TypeError en producción: los kwargs con los que `handlers`
    llama al detector en el join deben poder enlazarse con su firma. Un nombre
    mal escrito aquí solo se vería al entrar un usuario real."""
    import ast
    import inspect
    from pathlib import Path

    ruta = Path(__file__).resolve().parents[1] / "src" / "handlers.py"
    fuente = ast.parse(ruta.read_text(encoding="utf-8"))
    llamadas = [
        n for n in ast.walk(fuente)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "check"
        and getattr(n.func.value, "id", "") == "personal_channel_det"
    ]
    assert llamadas, "handlers.py ya no llama a personal_channel_det.check"
    for llamada in llamadas:
        kwargs = {kw.arg for kw in llamada.keywords if kw.arg}
        inspect.signature(pc.check).bind(
            "titulo", **dict.fromkeys(kwargs, None),
        )


def test_lista_editable_del_repo_caza_el_caso_real():
    """La lista versionada en config/blacklist/ debe cubrir el término del caso
    real; si alguien la vacía, este test avisa."""
    assert pc._keywords_re().search(CANAL_REAL)
