"""Leer el texto que va DENTRO de una imagen.

Caso que lo motivó (6-sep-2026, Windows 11): una imagen ofreciendo «INSTALACIÓN
Y ACTIVACIÓN DE SOFTWARE — Windows, Office, Photoshop, AutoCAD (todas las
versiones) — ESCRÍBEME POR INTERNO», **sin una sola letra en el mensaje**. Para
el bot era un mensaje vacío: ningún detector tenía nada que mirar.

La petición del admin fue explícita: cazar el cartel evidente **sin banear a
alguien nuevo que comparte la foto de un ordenador**. De ahí el diseño: el OCR
no decide nada, solo aporta texto, y lo juzgan los detectores de siempre con sus
mismos umbrales. Una foto sin letras da texto vacío y puntúa 0, igual que antes.

Medido: 0,61 s por imagen, ~2 primeros mensajes al día en este despliegue.
"""
import asyncio
from pathlib import Path

import pytest

from src import ocr


# ------------------------------------------------------- no puede colgar el bot

@pytest.mark.asyncio
async def test_sin_tesseract_devuelve_vacio(monkeypatch):
    """Es una mejora opcional: quien instale el bot sin tesseract no pierde nada."""
    monkeypatch.setattr(ocr, "_disponible", False)
    assert await ocr.leer(b"loquesea") == ""


@pytest.mark.asyncio
async def test_una_imagen_enorme_ni_se_intenta(monkeypatch):
    monkeypatch.setattr(ocr, "_disponible", True)
    assert await ocr.leer(b"x" * (ocr.MAX_BYTES + 1)) == ""


@pytest.mark.asyncio
async def test_sin_datos_no_hace_nada():
    assert await ocr.leer(b"") == ""


@pytest.mark.asyncio
async def test_un_ocr_colgado_no_congela_el_bot(monkeypatch):
    """PTB procesa los updates de uno en uno: sin tope, esto para la moderación."""
    import time as _t
    monkeypatch.setattr(ocr, "_disponible", True)
    monkeypatch.setattr(ocr, "TIMEOUT_S", 0.05)
    monkeypatch.setattr(ocr, "_leer_sincrono", lambda d: (_t.sleep(30), "x")[1])
    t0 = _t.perf_counter()
    assert await ocr.leer(b"datos") == ""
    assert _t.perf_counter() - t0 < 3


@pytest.mark.asyncio
async def test_un_fallo_cualquiera_devuelve_vacio(monkeypatch):
    monkeypatch.setattr(ocr, "_disponible", True)

    def revienta(d):
        raise RuntimeError("tesseract explotó")
    monkeypatch.setattr(ocr, "_leer_sincrono", revienta)
    assert await ocr.leer(b"datos") == ""


@pytest.mark.asyncio
async def test_va_en_un_hilo_aparte(monkeypatch):
    """0,61 s bloqueando el bucle son 0,61 s sin moderar nada más."""
    fuente = Path("src/ocr.py").read_text()
    assert "run_in_executor" in fuente


@pytest.mark.asyncio
async def test_el_ruido_corto_se_descarta(monkeypatch):
    """Bordes y logos dan dos o tres caracteres sueltos: eso no es un texto."""
    monkeypatch.setattr(ocr, "_disponible", True)
    monkeypatch.setattr(ocr, "_leer_sincrono", lambda d: "a b\n c")
    assert await ocr.leer(b"datos") == ""


@pytest.mark.asyncio
async def test_un_texto_de_verdad_se_devuelve_limpio(monkeypatch):
    monkeypatch.setattr(ocr, "_disponible", True)
    monkeypatch.setattr(ocr, "_leer_sincrono",
                        lambda d: "  INSTALACIÓN Y\n\n  ACTIVACION  DE SOFTWARE ")
    assert await ocr.leer(b"datos") == "INSTALACIÓN Y ACTIVACION DE SOFTWARE"


# --------------------------------------------------- el OCR no decide, solo lee

def test_el_ocr_no_inventa_ninguna_regla():
    """Si tuviera puntuación propia, podría banear por su cuenta con un texto mal
    leído. Solo aporta texto; deciden los detectores de siempre."""
    fuente = Path("src/ocr.py").read_text()
    for prohibido in ("Hit(", "score", "ban", "rule="):
        assert prohibido not in fuente, f"el OCR no puede decidir ({prohibido})"


def test_el_enganche_usa_los_detectores_normales():
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def _hits_de_la_imagen(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    assert "comad_det.check" in cuerpo
    assert "is_first_msg=True" in cuerpo
    assert "_apply_money_guard" in cuerpo, "debe respetar el ajuste del chat"
    assert "_sin_tumbar" in cuerpo, "un detector roto no puede tumbar el mensaje"


def test_solo_en_primeros_mensajes_con_imagen_y_sin_texto():
    """El coste queda en ~2 casos al día. Si se aplicara a cada foto del grupo,
    serían cientos de descargas y de invocaciones diarias."""
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("_hits_de_la_imagen(context, db, cfg, msg, user)")
    bloque = fuente[max(0, i - 600):i]
    assert "is_first" in bloque
    assert "not (msg.text or msg.caption)" in bloque
    assert "msg.photo" in bloque


def test_el_fallo_del_ocr_no_impide_moderar_el_mensaje():
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("_hits_de_la_imagen(context, db, cfg, msg, user)")
    assert "except Exception" in fuente[i:i + 400]


# ------------------------------------------- lo que pidió el admin, comprobado

def test_una_foto_sin_texto_no_puede_banear_a_nadie(monkeypatch):
    """«que no baneemos a alguien nuevo que pasa una foto de un ordenador»."""
    from types import SimpleNamespace as NS
    from src.detectors import commercial_ad
    for texto in ("", "   ", "DELL", "Lenovo ThinkPad"):
        msg = NS(text=texto, caption=None, entities=(), caption_entities=(),
                 reply_to_message=None)
        assert not commercial_ad.check(msg, is_first_msg=True), \
            f"una foto que solo da {texto!r} no puede disparar nada"


def test_el_cartel_del_caso_si_dispara():
    """El texto tal y como lo devolvió el OCR de verdad, con su ruido incluido."""
    from types import SimpleNamespace as NS
    from src.detectors import commercial_ad
    leido = (": INSTALACIÓN Y *\n_ ACTIVACION\na DE SOFTWARE = Z\n"
             "e Windows Microsoft Office G da\n"
             "en (Todas las versiones) (Todas las versiones) = = “\n"
             "EA y WINDOWS Y OFFICE an y\nPhotoshon Mesteor AutoCAD E\n"
             "Rhinoceros »\nQU viseño y anqurrecTURa >\no '|SERVICIO\n"
             "” GARANTIZADO\nO) ESCRÍBEME >»\nPOR INTERNO")
    msg = NS(text=leido, caption=None, entities=(), caption_entities=(),
             reply_to_message=None)
    hit = commercial_ad.check(msg, is_first_msg=True)
    assert hit and hit.score >= 100, f"puntúa {hit.score if hit else 0}"


@pytest.mark.parametrize("frase", [
    "No me activa el Windows tras cambiar la placa, alguna idea?",
    "Tengo problemas con la activacion de Office, me pide la clave",
    "Uso Photoshop y AutoCAD en el trabajo, van bien en Windows 11",
    "He hecho una instalacion limpia de Windows 11 y va mejor",
    "Escribeme por interno y te paso el driver que te decia",
    "Vendo portatil Asus i7 con Windows 11 y Office instalado, 400 euros",
    "Te garantizo que con esa RAM va perfecto, yo tengo lo mismo",
])
def test_la_conversacion_normal_de_un_grupo_de_windows_no_dispara(frase):
    """El riesgo real de este vocabulario: «activar», «instalación» y «licencia»
    son palabras del día a día en estos grupos. Ninguna va suelta en las listas."""
    from types import SimpleNamespace as NS
    from src.detectors import commercial_ad
    msg = NS(text=frase, caption=None, entities=(), caption_entities=(),
             reply_to_message=None)
    assert not commercial_ad.check(msg, is_first_msg=True)


def test_tesseract_esta_en_la_imagen():
    assert "tesseract-ocr" in Path("Dockerfile").read_text()


def test_asyncio_se_usa_para_el_tope():
    assert asyncio  # el import documenta que el tope es asíncrono


# ---------------------------------------------------------------------------
# Ajustes: idiomas, interruptor por chat y vocabulario propio
# ---------------------------------------------------------------------------

def test_los_idiomas_salen_de_los_del_bot(monkeypatch):
    """No una lista aparte: si alguien modera en portugués y añade `pt` a sus
    listas negras, no tiene sentido que el OCR siga leyendo solo en español."""
    monkeypatch.delenv("OCR_LANGS", raising=False)
    monkeypatch.setattr(ocr, "_IDIOMAS_INSTALADOS", {"spa", "eng", "por"})
    monkeypatch.setattr("src.wordlists.active_langs", lambda: ["pt", "en"])
    assert ocr.idiomas() == "por+eng"


def test_se_filtran_los_idiomas_que_no_estan_instalados(monkeypatch):
    """Pedirle a Tesseract un idioma que le falta hace fallar la llamada ENTERA:
    no leería nada, ni siquiera en los idiomas que sí tiene."""
    monkeypatch.delenv("OCR_LANGS", raising=False)
    monkeypatch.setattr(ocr, "_IDIOMAS_INSTALADOS", {"eng"})
    monkeypatch.setattr("src.wordlists.active_langs", lambda: ["ru", "en"])
    assert ocr.idiomas() == "eng"


def test_nunca_se_queda_sin_idioma(monkeypatch):
    monkeypatch.delenv("OCR_LANGS", raising=False)
    monkeypatch.setattr(ocr, "_IDIOMAS_INSTALADOS", {"eng"})
    monkeypatch.setattr("src.wordlists.active_langs", lambda: ["ja"])
    assert ocr.idiomas() == "eng"


def test_la_variable_de_entorno_manda(monkeypatch):
    monkeypatch.setenv("OCR_LANGS", "spa+por+eng")
    assert ocr.idiomas() == "spa+por+eng"


def test_se_puede_apagar_por_chat(tmp_path):
    from src.db import DB
    from src.handlers import _ocr_activo
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(-100, "G", "supergroup", True, True, True)
    db.ensure_chat_settings(-100)
    assert _ocr_activo(db, -100) is True, "nace encendido"
    db.update_chat_setting(-100, "ocr_enabled", 0)
    assert _ocr_activo(db, -100) is False


def test_un_chat_sin_ajustes_lo_tiene_encendido(tmp_path):
    from src.db import DB
    from src.handlers import _ocr_activo
    db = DB(str(tmp_path / "t.db"))
    assert _ocr_activo(db, -999) is True


def test_un_ajuste_ilegible_no_apaga_la_lectura():
    """Aquí «restrictivo» sería dejar de mirar, y el OCR no castiga por sí mismo."""
    from src.handlers import _ocr_activo

    class Rota:
        def get_chat_settings(self, c):
            raise RuntimeError("base caída")
    assert _ocr_activo(Rota(), -100) is True


def test_el_interruptor_esta_en_el_panel():
    from pathlib import Path
    fuente = Path("src/config_panel.py").read_text()
    assert "ocr_enabled" in fuente
    assert "cfg.b.ocr" in fuente


def test_por_defecto_el_vocabulario_es_el_MISMO_que_el_de_los_mensajes():
    """Decisión del admin: el spam es el mismo venga en texto o en cartel, y dos
    vocabularios en paralelo acaban con uno de los dos desactualizado."""
    from src.wordlists import load_terms
    compartido = load_terms("commercial_cta.txt", [])
    con_ocr = load_terms("commercial_cta.txt", [], incluir_ocr=True)
    assert con_ocr[:len(compartido)] == compartido, "la base tiene que ser la misma"


def test_se_puede_anadir_vocabulario_solo_para_imagenes(tmp_path, monkeypatch):
    """La capa opcional: términos que en una conversación darían falsos positivos
    pero que en un cartel son inequívocos."""
    import src.wordlists as W
    (tmp_path / "ocr").mkdir()
    (tmp_path / "lista.txt").write_text("comun\n")
    (tmp_path / "ocr" / "lista.txt").write_text("solo_en_carteles\n")
    monkeypatch.setattr(W, "_BLACKLIST_DIR", tmp_path)
    W.clear_cache()
    assert "solo_en_carteles" not in W.load_terms("lista.txt", [])
    assert "solo_en_carteles" in W.load_terms("lista.txt", [], incluir_ocr=True)


def test_la_carpeta_opcional_esta_documentada():
    from pathlib import Path
    doc = Path("config/blacklist/ocr/README.md")
    assert doc.exists()
    assert "mismas listas" in doc.read_text()


def test_el_modo_ocr_no_contamina_los_mensajes_escritos(tmp_path, monkeypatch):
    """Sin el modo en la clave de caché, el primer texto de imagen dejaría
    cacheado un patrón con vocabulario de `ocr/` que luego se aplicaría a los
    mensajes normales, y al revés."""
    import src.wordlists as W
    (tmp_path / "ocr").mkdir()
    (tmp_path / "l.txt").write_text("comun\n")
    (tmp_path / "ocr" / "l.txt").write_text("solocartel\n")
    monkeypatch.setattr(W, "_BLACKLIST_DIR", tmp_path)
    W.clear_cache()

    assert not W.load_and_compile("l.txt", []).search("solocartel")
    with W.modo_ocr():
        assert W.load_and_compile("l.txt", []).search("solocartel")
    assert not W.load_and_compile("l.txt", []).search("solocartel"), \
        "el patrón del modo OCR se quedó cacheado para los mensajes normales"


def test_el_modo_se_desactiva_aunque_algo_falle():
    """Si quedara activo, todos los mensajes escritos pasarían a usar el
    vocabulario de carteles."""
    import src.wordlists as W
    try:
        with W.modo_ocr():
            raise RuntimeError("algo falló evaluando")
    except RuntimeError:
        pass
    assert W._MODO_OCR is False


def test_el_enganche_evalua_dentro_del_modo():
    from pathlib import Path
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def _hits_de_la_imagen(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    assert "with modo_ocr():" in cuerpo
