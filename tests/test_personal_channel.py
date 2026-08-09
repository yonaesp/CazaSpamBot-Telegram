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


# --- Caso real 2026-07-27: la red 财天下 con NOMBRE tambien en chino -----------
# El detector nacio contra «Matthew» (nombre latino + canal chino = discordancia).
# Esta variante lleva el nombre TAMBIEN en chino, asi que no hay discordancia y se
# colaba con 40 puntos de 100. Lo que la delata es el vocabulario del titulo y que
# bio y usuario son cadenas generadas a maquina ("bhLQZZXwkU2M").

def test_red_caitianxia_con_nombre_chino_se_caza():
    h = pc.check("财天下集团飞机加群结账通知频道", first_name="属棋却仁",
                 username="znhlOOWcZYYS", bio="bhLQZZXwkU2M",
                 has_photo=True, has_bio=True, allowed_scripts=("latin",))
    assert h.score >= 100, f"se cuela con score={h.score}"
    assert h.rule == "personal_channel_spam"


@pytest.mark.parametrize("texto,esperado", [
    ("bhLQZZXwkU2M", True),      # bio del caso real
    ("znhlOOWcZYYS", True),      # usuario del caso real
    ("UjgVpcyOVlbLyy", True),    # otra cuenta de la misma red
    # Legitimos: incluidos idiomas con rachas largas de consonantes, que son el
    # falso positivo obvio de esta heuristica.
    ("carlosmartinez", False),
    ("Krzysztof_Brzeczyszczykiewicz", False),
    ("wchrzszcz", False),        # polaco SIN VOCALES: el falso positivo obvio
    ("MariaGARCIA", False),      # apellido en mayúsculas al final
    ("JohnDOE", False),
    ("NASA", False),             # acrónimo
    ("sergeybazhenovvv", False),
    ("maria_lopez", False),
    ("CarLogistEsp", False),
    ("xd", False),               # demasiado corto para decidir
])
def test_deteccion_de_cadenas_generadas(texto, esperado):
    assert pc._parece_generada(texto) is esperado


def test_cadena_generada_sola_no_banea():
    """Es senial de APOYO: sin canal sospechoso no debe disparar nada, o marcaria
    a cualquiera con un usuario raro."""
    h = pc.check(None, first_name="Ana", username="xK9mPzQwRtY",
                 has_photo=False, has_bio=False, allowed_scripts=("latin",))
    assert h.score == 0


@pytest.mark.parametrize("titulo", [
    "我的摄影频道",              # "mi canal de fotografia"
    "北京美食推荐",              # "recomendaciones de comida de Pekin"
    "结账系统更新公告",          # lleva 结账 SUELTO: no debe bastar
])
def test_titulos_chinos_legitimos_no_disparan_por_keyword(titulo):
    assert not pc._keywords_re().search(titulo)


@pytest.mark.parametrize("titulo", [
    "财天下集团飞机加群结账通知频道",
    "恒泰集团招洗钱车队结账通知频道",
    "财哥【财赢天下】加群带走600",
])
def test_titulos_de_la_red_si_disparan(titulo):
    assert pc._keywords_re().search(titulo)


# ---------------------------------------------------------------------------
# La red renombra sus canales, y el rótulo deja de valer
#
# Medido el 2026-08-08 en Windows 11: «Vickycat46», nombre latino y foto de
# perfil normal, con el canal `恒泰招聘车队高速结算`. Sumaba 85 de 100 y se
# libraba JUSTO por tener foto (los 25 de «perfil sin nada que mirar» no
# aplicaban). Ninguna palabra de la lista casaba: la red había cambiado
# `洗钱车队结账` por `招聘车队...结算`.
#
# De ahí las dos costuras nuevas: vocabulario al día y, sobre todo, mirar lo que
# el canal PUBLICA, que es donde dice a qué se dedica de verdad.
# ---------------------------------------------------------------------------

_POST_REAL = (
    "洗米来有码就要 无风险 日3-8k\n\n接受一切方式有微信支付宝就来\n\n"
    "飞哥客服：@Dl88o 认准ID私信\n担保公群 https://t.me/+yQ_Y6e7TJP85ZTQx"
)


def test_el_caso_vickycat_ya_no_se_escapa_por_tener_foto():
    h = pc.check("恒泰招聘车队高速结算", first_name="Vickycat46",
                 has_photo=True, has_bio=False, allowed_scripts=("latin",))
    assert h, "con foto de perfil seguía colándose"
    assert h.rule == "personal_channel_spam"


def test_aunque_renombren_el_canal_lo_delata_lo_que_publica():
    """La defensa de fondo: el título lo elige el spammer sabiendo que se ve."""
    sin_contenido = pc.check("Mi canal personal", first_name="Vickycat46",
                             has_photo=True, has_bio=False, allowed_scripts=("latin",))
    assert not sin_contenido, "un título anodino no debe bastar por sí solo"
    # Con un título ajeno pero limpio, lo que publica cierra el caso.
    con_contenido = pc.check("每日更新频道", first_name="Vickycat46",
                             has_photo=True, has_bio=False, allowed_scripts=("latin",),
                             channel_text=_POST_REAL)
    assert con_contenido, "el contenido del canal debería haberlo cazado"
    assert (con_contenido.payload or {}).get("channel_content") is True


def test_el_contenido_del_canal_no_decide_solo():
    """Regla del proyecto: ninguna señal suelta llega al umbral. Un canal en el
    alfabeto del grupo, con nombre normal y foto, no cae por una frase."""
    h = pc.check("Ofertas de curro", first_name="Ana", has_photo=True, has_bio=True,
                 bio="Vivo en Madrid", allowed_scripts=("latin",),
                 channel_text="money laundering para todos")
    assert not h, "75 puntos no pueden alcanzar MIN_SCORE=100"


def test_un_canal_legitimo_con_posts_normales_no_dispara():
    h = pc.check("Fotos de montaña", first_name="Ana", has_photo=False, has_bio=False,
                 allowed_scripts=("latin",),
                 channel_text="Ruta de ayer por Peñalara, 14 km y mucho barro")
    assert not h


def test_sin_contenido_se_comporta_igual_que_antes():
    """El parámetro es opcional a propósito: leer el canal cuesta una llamada de
    red y solo se paga cuando el título no ha bastado."""
    args = dict(first_name="Witte", has_photo=False, has_bio=False, allowed_scripts=("latin",))
    a = pc.check("财天下集团飞机加群结账通知频道", **args)
    b = pc.check("财天下集团飞机加群结账通知频道", channel_text=None, **args)
    assert a.score == b.score


@pytest.mark.parametrize("titulo", [
    "恒泰招聘车队高速结算",          # Vickycat46
    "恒泰集团招聘车队高效结算",      # otras dos cuentas de la misma red
])
def test_los_titulos_renombrados_de_la_red_ya_casan(titulo):
    assert pc._keywords_re().search(titulo)


@pytest.mark.parametrize("texto", [
    "招聘车队司机，五险一金",        # oferta de trabajo REAL para conductores
    "北京招聘会 3月15日",            # feria de empleo
    "今日结算完成",                  # "liquidación de hoy completada"
    "车队出发了",                    # "la flota ha salido"
])
def test_chino_laboral_normal_no_casa(texto):
    """Anti falso positivo: reclutar conductores es una actividad legítima. Lo
    que delata a la red es el compuesto entero, no `车队` ni `招聘` sueltos."""
    casa = pc._keywords_re().search(texto)
    assert not casa or casa.group(0) not in ("车队", "招聘", "结算")


@pytest.mark.parametrize("texto", [
    "日3-8k",                        # el post de Vickycat46
    "日结500-2000",                  # variante habitual
])
def test_ingresos_diarios_con_cifra_pegada_si_casan(texto):
    assert pc._keywords_re().search(texto)


@pytest.mark.parametrize("texto", [
    "8月9日 10-12点 直播",           # una FECHA con horario: no es una oferta
    "生日快乐",
])
def test_fechas_y_texto_corriente_no_casan_como_ingresos(texto):
    casa = pc._keywords_re().search(texto)
    assert not casa, f"falso positivo: {casa.group(0) if casa else ''}"
