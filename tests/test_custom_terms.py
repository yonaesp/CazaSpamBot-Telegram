"""Términos personalizados: literales de verdad, caché viva y anti falso positivo.

Lo que se protege aquí, por orden de gravedad si se rompiera:

1. Que nada de lo que entre por esta vía se interprete como regex. Un `.*`
   colado en una lista negra banea al grupo entero.
2. Que sin archivos personalizados el bot se comporte EXACTAMENTE igual que
   antes (es producción: miles de usuarios reales).
3. Que un cambio tenga efecto sin reiniciar, o el admin creerá que el bot le
   ignora y acabará añadiendo el término tres veces.
4. Que el archivo lo pueda destrozar un humano con un editor sin tumbar nada.
"""
from __future__ import annotations

import pytest

from src import custom_terms, wordlists

LISTA = "commercial_work.txt"
LISTA_SIN_BORDES = "commercial_money.txt"


@pytest.fixture(autouse=True)
def _blacklist_aislada(tmp_path, monkeypatch):
    """Directorio de listas propio: ni tocamos las del repo ni nos contaminamos."""
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    wordlists.clear_cache()
    yield
    wordlists.clear_cache()


def _custom(filename: str, body: str) -> None:
    """Escribe el archivo personalizado a mano, como haría un humano."""
    path = wordlists.custom_file(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


# ---------- 1. literales, nunca regex ----------

def test_los_metacaracteres_son_literales_no_patrones():
    """`.` es un punto y `*` un asterisco: si se interpretaran, `oferta.*` casaría
    con cualquier mensaje que contenga 'oferta'."""
    assert custom_terms.add_term(LISTA, "oferta.*brutal").ok
    rx = wordlists.load_and_compile(LISTA, [])
    assert rx.search("una oferta.*brutal de verdad")
    assert not rx.search("una oferta cualquiera brutal")


def test_el_porcentaje_y_los_parentesis_funcionan_tal_cual():
    assert custom_terms.add_term(LISTA, "oferta 100% garantizada").ok
    assert custom_terms.add_term(LISTA, "gana dinero (rapido) hoy").ok
    rx = wordlists.load_and_compile(LISTA, [])
    assert rx.search("te traigo una OFERTA 100% GARANTIZADA hoy")
    assert rx.search("puedes gana dinero (rapido) hoy desde casa")


def test_un_comodin_escrito_a_mano_en_el_archivo_tampoco_es_regex():
    """La garantía vale aunque nadie pase por la API: se escapa AL CARGAR."""
    _custom(LISTA, ".*\n")
    rx = wordlists.load_and_compile(LISTA, [])
    assert not rx.search("un mensaje totalmente normal del grupo")


def test_una_alternancia_escrita_a_mano_no_secuestra_la_lista():
    _custom(LISTA, "casino|.+\n")
    rx = wordlists.load_and_compile(LISTA, [])
    assert not rx.search("hola buenas tardes a todos")


# ---------- 2. retrocompatibilidad ----------

def test_sin_archivos_custom_no_cambia_absolutamente_nada(tmp_path):
    (tmp_path / "l.txt").write_text("casino\nforex\n", encoding="utf-8")
    assert wordlists.load_terms("l.txt", ["fallback"], langs=["en"]) == ["casino", "forex"]


def test_sin_archivos_custom_se_siguen_usando_los_defaults(tmp_path):
    assert wordlists.load_terms("no_existe.txt", ["a", "b"], langs=[]) == ["a", "b"]


def test_los_custom_se_acumulan_sobre_repo_e_idioma(tmp_path):
    """Se suman, no sustituyen: el admin añade a lo que ya protege."""
    (tmp_path / LISTA).write_text("casino\n", encoding="utf-8")
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / LISTA).write_text("now hiring\n", encoding="utf-8")
    _custom(LISTA, "chiringuito financiero\n")
    assert wordlists.load_terms(LISTA, [], langs=["en"]) == [
        "casino", "now hiring", "chiringuito\\ financiero",
    ]


def test_un_custom_duplicado_del_repo_no_se_repite(tmp_path):
    (tmp_path / LISTA).write_text("casino\n", encoding="utf-8")
    _custom(LISTA, "casino\n")
    assert wordlists.load_terms(LISTA, [], langs=[]) == ["casino"]


# ---------- 3. la caché se invalida sola ----------

def test_un_termino_anadido_hace_efecto_sin_reiniciar():
    """Antes de añadir, el patrón ya está compilado y cacheado: si la caché no se
    invalidara, el término nuevo no haría nada hasta el siguiente reinicio."""
    rx = wordlists.load_and_compile(LISTA, ["casino"])
    assert not rx.search("vendo relojes de imitacion")

    custom_terms.add_term(LISTA, "relojes de imitacion")

    assert wordlists.load_and_compile(LISTA, ["casino"]).search("vendo relojes de imitacion")


def test_un_termino_quitado_deja_de_cazar_sin_reiniciar():
    custom_terms.add_term(LISTA, "relojes de imitacion")
    assert wordlists.load_and_compile(LISTA, []).search("vendo relojes de imitacion")

    custom_terms.remove_term(LISTA, "relojes de imitacion")

    assert not wordlists.load_and_compile(LISTA, []).search("vendo relojes de imitacion")


def test_una_edicion_a_mano_del_archivo_tambien_se_recoge():
    """La huella (mtime + tamaño) va en la clave de caché, así que ni siquiera
    hace falta pasar por la API para que el cambio entre."""
    assert not wordlists.load_and_compile(LISTA, []).search("compra oro barato")
    _custom(LISTA, "compra oro barato\n")
    assert wordlists.load_and_compile(LISTA, []).search("compra oro barato")


def test_la_cache_no_crece_sin_limite_al_editar():
    """Cada edición sustituye la versión anterior, no la acumula."""
    for i in range(6):
        custom_terms.add_term(LISTA, f"termino numero {i}")
        wordlists.load_and_compile(LISTA, [])
    claves = [k for k in wordlists._COMPILED if k[0] == LISTA]
    assert len(claves) == 1


# ---------- 4. validaciones ----------

@pytest.mark.parametrize("termino", ["", "   ", "\n\t "])
def test_rechaza_vacios(termino):
    assert custom_terms.add_term(LISTA, termino).code == custom_terms.ERR_EMPTY


@pytest.mark.parametrize("termino", ["ab", "ya", "pin"])
def test_rechaza_terminos_peligrosamente_cortos(termino):
    """Un término de 2 o 3 letras casa con media conversación."""
    assert custom_terms.add_term(LISTA, termino).code == custom_terms.ERR_TOO_SHORT


@pytest.mark.parametrize("termino", ["!!!!!", "-----", "?? ?? ??"])
def test_rechaza_lo_que_es_solo_signos(termino):
    assert custom_terms.add_term(LISTA, termino).code == custom_terms.ERR_NO_TEXT


def test_rechaza_terminos_kilometricos():
    assert custom_terms.add_term(LISTA, "spam " * 40).code == custom_terms.ERR_TOO_LONG


def test_rechaza_duplicados_ignorando_mayusculas():
    assert custom_terms.add_term(LISTA, "trabajo desde casa").ok
    assert custom_terms.add_term(LISTA, "TRABAJO DESDE CASA").code == custom_terms.ERR_DUPLICATE
    assert custom_terms.list_terms(LISTA) == ["trabajo desde casa"]


def test_rechaza_lo_que_las_listas_del_repo_ya_cazan(tmp_path):
    """Añadirlo solo engordaría la alternancia que corre en cada mensaje."""
    (tmp_path / LISTA).write_text(r"gana\s+dinero", encoding="utf-8")
    assert custom_terms.add_term(LISTA, "gana dinero").code == custom_terms.ERR_ALREADY_COVERED


def test_rechaza_terminos_que_empiezan_o_acaban_en_simbolo():
    """`\\b(?:...)\\b` nunca casa junto a un símbolo: quedaría muerto en silencio."""
    assert custom_terms.add_term(LISTA, "€500 al mes").code == custom_terms.ERR_SYMBOL_EDGES
    assert custom_terms.add_term(LISTA, "gana mucho!").code == custom_terms.ERR_SYMBOL_EDGES


def test_en_las_listas_de_importes_si_se_admite_empezar_por_simbolo():
    """Esas dos listas se cargan sin envoltorio justo para eso."""
    assert custom_terms.add_term(LISTA_SIN_BORDES, "€500 al mes").ok


def test_tope_de_terminos_por_lista(monkeypatch):
    monkeypatch.setattr(custom_terms, "MAX_TERMS_PER_LIST", 3)
    for i in range(3):
        assert custom_terms.add_term(LISTA, f"termino numero {i}").ok
    assert custom_terms.add_term(LISTA, "uno mas").code == custom_terms.ERR_LIST_FULL


def test_lista_desconocida_no_escribe_nada():
    """El nombre llega desde un callback de Telegram: sin lista blanca, un
    `../../` escribiría donde quisiera quien lo mandara."""
    for nombre in ("../../../etc/passwd", "inventada.txt", "classifier_excluded_tokens.txt"):
        assert custom_terms.add_term(nombre, "cualquier cosa").code == custom_terms.ERR_UNKNOWN_LIST
        assert custom_terms.list_terms(nombre) == []


def test_normaliza_espacios_sobrantes_del_copia_pega():
    res = custom_terms.add_term(LISTA, "  gana   mucho    dinero  ")
    assert res.term == "gana mucho dinero"
    assert custom_terms.list_terms(LISTA) == ["gana mucho dinero"]


def test_quitar_un_termino_que_no_existe_avisa():
    assert custom_terms.remove_term(LISTA, "nunca estuvo").code == custom_terms.ERR_NOT_FOUND


def test_quitar_ignora_mayusculas_y_espacios():
    custom_terms.add_term(LISTA, "gana mucho dinero")
    assert custom_terms.remove_term(LISTA, "  GANA MUCHO DINERO ").ok
    assert custom_terms.list_terms(LISTA) == []


# ---------- 5. vista previa ----------

def _grupo_con_mensajes(db, mensajes: list[str], chat_id: int = -100) -> None:
    for i, texto in enumerate(mensajes, start=1):
        db.record_message(chat_id, 1000 + i, f"user{i}")
        db.update_last_message(chat_id, 1000 + i, i, texto)


def test_la_vista_previa_cuenta_las_coincidencias_reales(tmp_db):
    _grupo_con_mensajes(tmp_db, [
        "alguien sabe si hay oferta de Echo Dot esta semana?",
        "vi una oferta buenisima en Amazon ayer",
        "he actualizado a Windows 11 y va fino",
        "la grafica me va fatal desde el ultimo driver",
    ])
    prev = custom_terms.preview_term(tmp_db, LISTA, "oferta")
    assert prev.scanned == 4
    assert prev.matches == 2
    assert len(prev.examples) == 2
    assert prev.risky


def test_la_vista_previa_no_cuenta_de_mas_con_un_termino_especifico(tmp_db):
    _grupo_con_mensajes(tmp_db, [
        "alguien sabe si hay oferta de Echo Dot esta semana?",
        "trabajo desde casa como programador, nada raro",
    ])
    prev = custom_terms.preview_term(tmp_db, LISTA, "chiringuito financiero")
    assert prev.scanned == 2
    assert prev.matches == 0
    assert prev.examples == ()
    assert not prev.risky


def test_la_vista_previa_puede_filtrar_por_grupo(tmp_db):
    _grupo_con_mensajes(tmp_db, ["hay oferta de teclados"], chat_id=-111)
    _grupo_con_mensajes(tmp_db, ["hay oferta de ratones"], chat_id=-222)
    assert custom_terms.preview_term(tmp_db, LISTA, "oferta").matches == 2
    assert custom_terms.preview_term(tmp_db, LISTA, "oferta", chat_id=-111).matches == 1


def test_la_vista_previa_avisa_si_caza_un_mensaje_marcado_como_legitimo(tmp_db):
    """Un `ham` que coincide es un falso positivo confirmado por el propio admin."""
    tmp_db.add_sample("me gusta esta oferta de teclados", "h1", "ham", 1, -100, 5)
    prev = custom_terms.preview_term(tmp_db, LISTA, "oferta")
    assert prev.ham_hits == 1
    assert prev.risky


def test_la_vista_previa_respeta_el_limite_de_mensajes(tmp_db):
    _grupo_con_mensajes(tmp_db, [f"mensaje con oferta numero {i}" for i in range(30)])
    prev = custom_terms.preview_term(tmp_db, LISTA, "oferta", scan_limit=10)
    assert prev.scanned == 10
    assert prev.matches == 10


def test_la_vista_previa_trata_el_termino_como_literal(tmp_db):
    _grupo_con_mensajes(tmp_db, ["hola que tal todo el mundo", "hasta luego gente"])
    prev = custom_terms.preview_term(tmp_db, LISTA, "hola.*luego")
    assert prev.matches == 0


def test_la_vista_previa_de_un_termino_invalido_no_busca(tmp_db):
    _grupo_con_mensajes(tmp_db, ["hola que tal"])
    prev = custom_terms.preview_term(tmp_db, LISTA, "  ")
    assert not prev.valid.ok
    assert prev.scanned == 0 and prev.matches == 0


def test_la_vista_previa_sobrevive_a_una_db_rota():
    """Es informativa: si la consulta falla, el panel no puede caerse."""
    class DBRota:
        def recent_message_texts(self, **kw):
            raise RuntimeError("disco ocupado")

        def recent_sample_texts(self, *a, **kw):
            raise RuntimeError("disco ocupado")

    prev = custom_terms.preview_term(DBRota(), LISTA, "oferta especial")
    assert prev.scanned == 0 and prev.matches == 0


def test_los_ejemplos_se_recortan_para_no_inundar_el_chat(tmp_db):
    _grupo_con_mensajes(tmp_db, ["oferta " + "muy larga " * 40])
    ejemplo = custom_terms.preview_term(tmp_db, LISTA, "oferta").examples[0]
    assert len(ejemplo) <= 120 and ejemplo.endswith("…")


# ---------- 6. el archivo lo puede destrozar un humano ----------

def test_lineas_vacias_y_comentarios_se_ignoran():
    _custom(LISTA, "# mis terminos\n\n  \ncasino ilegal\n\n# otro comentario\n")
    assert custom_terms.list_terms(LISTA) == ["casino ilegal"]


def test_basura_binaria_y_caracteres_raros_no_rompen_la_carga():
    _custom(LISTA, "\x00\x01basura\ncasino ilegal\n﻿\U0001f4a9\n")
    rx = wordlists.load_and_compile(LISTA, ["fallback"])
    assert rx.search("esto es un casino ilegal")


def test_un_archivo_en_otra_codificacion_no_tumba_el_bot():
    """Guardado en latin-1 (o con un byte suelto de un copia y pega): se pierde
    el carácter ilegible, NO la lista entera ni el arranque del detector."""
    path = wordlists.custom_file(LISTA)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("caf\xe9 ilegal\ncasino ilegal\n".encode("latin-1"))
    assert "casino ilegal" in custom_terms.list_terms(LISTA)
    assert wordlists.load_and_compile(LISTA, ["forex"]).search("esto es un casino ilegal")


def test_un_termino_con_acentos_se_guarda_y_caza_bien():
    """UTF-8 de principio a fin: el castellano lleva acentos y eñes."""
    assert custom_terms.add_term(LISTA, "inversión garantizada").ok
    assert custom_terms.list_terms(LISTA) == ["inversión garantizada"]
    assert wordlists.load_and_compile(LISTA, []).search("una INVERSIÓN GARANTIZADA")


def test_un_archivo_gigante_se_recorta():
    """Nadie puede dejar al bot masticando miles de ramas en CADA mensaje."""
    _custom(LISTA, "".join(f"termino numero {i}\n" for i in range(2000)))
    assert len(custom_terms.list_terms(LISTA)) == wordlists._CUSTOM_MAX_TERMS


def test_un_directorio_en_vez_de_archivo_no_lanza():
    wordlists.custom_file(LISTA).mkdir(parents=True)
    assert custom_terms.list_terms(LISTA) == []
    assert wordlists.load_and_compile(LISTA, ["forex"]).search("señales de forex")
