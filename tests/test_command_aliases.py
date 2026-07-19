"""Nombres de comando bilingües: alias en inglés y menú de Telegram por idioma.

El menú (`setMyCommands`) publica el nombre del comando en el idioma activo, así que
todo nombre publicado tiene que (a) existir como handler y (b) cumplir el formato que
exige Telegram. Si falla, el bot se queda SIN MENÚ, de ahí que se valide aquí.
"""
from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

from src import group_clean as gc
from src.i18n import SUPPORTED

_MAIN = Path(__file__).resolve().parent.parent / "src" / "main.py"

# Comandos con nombre traducible: (nombre en español, alias en inglés).
PARES = [
    ("verificacion", "verification"),
    ("idioma", "language"),
    ("alertas", "alerts"),
    ("limpieza", "cleanup"),
    ("comandos", "commands"),
    ("legal", "ham"),
]


def _handlers_registrados() -> dict[str, str]:
    """{nombre_comando: 'modulo.funcion'} leyendo los CommandHandler de main.py.

    Se hace por AST y no construyendo la Application: montar el bot de verdad exige
    token, base de datos y sesión, y aquí solo interesa qué se registra.
    """
    arbol = ast.parse(_MAIN.read_text(encoding="utf-8"))
    fuera: dict[str, str] = {}
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                and nodo.func.id == "CommandHandler" and len(nodo.args) >= 2):
            continue
        cmd, destino = nodo.args[0], nodo.args[1]
        if isinstance(cmd, ast.Constant) and isinstance(cmd.value, str):
            fuera[cmd.value] = ast.unparse(destino)
    return fuera


# ------------------------ alias en inglés ------------------------

def _resolver(ruta: str):
    """'admin.cmd_legal' → la función real, para comparar por identidad (hay alias
    de módulo como `cmd_ham = cmd_legal` que por texto no coincidirían)."""
    modulo, *atributos = ruta.split(".")
    obj = importlib.import_module(f"src.{modulo}")
    for a in atributos:
        obj = getattr(obj, a)
    return obj


@pytest.mark.parametrize("es,en", PARES)
def test_alias_ingles_registrado_y_mismo_handler(es, en):
    h = _handlers_registrados()
    assert es in h, f"/{es} dejó de estar registrado (es un bot en producción)"
    assert en in h, f"falta el alias /{en} de /{es}"
    assert _resolver(h[es]) is _resolver(h[en]), \
        f"/{en} apunta a {h[en]} pero /{es} a {h[es]}"


# ------------------------ menú de Telegram ------------------------

@pytest.mark.parametrize("lang", sorted(SUPPORTED))
@pytest.mark.parametrize("menu", ["_ADMIN_MENU", "_PUBLIC_MENU"])
def test_menu_nombres_validos_para_telegram(lang, menu):
    for c in gc._menu_commands(getattr(gc, menu), lang):
        assert re.match(r"^[a-z0-9_]{1,32}$", c.command), f"{lang}: nombre inválido {c.command!r}"
        assert c.description, f"{lang}: {c.command} sin descripción"


@pytest.mark.parametrize("lang", sorted(SUPPORTED))
@pytest.mark.parametrize("menu", ["_ADMIN_MENU", "_PUBLIC_MENU"])
def test_menu_sin_nombres_duplicados(lang, menu):
    nombres = [c.command for c in gc._menu_commands(getattr(gc, menu), lang)]
    assert len(nombres) == len(set(nombres)), f"{lang}: duplicados en {menu} → {nombres}"


@pytest.mark.parametrize("lang", sorted(SUPPORTED))
def test_todo_nombre_publicado_tiene_handler(lang):
    """De nada sirve publicar /alerts si nadie lo atiende."""
    h = _handlers_registrados()
    for c in gc._menu_commands(gc._ADMIN_MENU + gc._PUBLIC_MENU, lang):
        assert c.command in h, f"{lang}: el menú publica /{c.command} pero no hay handler"


def test_menu_en_ingles_usa_los_nombres_ingleses():
    nombres = {c.command for c in gc._menu_commands(gc._ADMIN_MENU, "en")}
    for es, en in PARES:
        assert en in nombres and es not in nombres, f"el menú en inglés debería traer /{en}"


def test_menu_en_espanol_mantiene_los_nombres_espanoles():
    nombres = {c.command for c in gc._menu_commands(gc._ADMIN_MENU, "es")}
    for es, _en in PARES:
        assert es in nombres, f"el menú en español debería traer /{es}"


# ------------------------ paquetes de idioma rotos ------------------------

def test_nombre_invalido_cae_al_por_defecto(monkeypatch):
    """Una traducción con acentos/mayúsculas/espacios no puede tumbar el menú."""
    from src import locales
    roto = dict(locales.STRINGS["es"])
    roto["cmd.name.verificacion"] = "Verificación de Usuarios"
    monkeypatch.setitem(locales.STRINGS, "xx", roto)
    assert gc._menu_name("verificacion", "xx") == "verificacion"
    for c in gc._menu_commands(gc._ADMIN_MENU, "xx"):
        assert re.match(r"^[a-z0-9_]{1,32}$", c.command)


def test_nombre_duplicado_en_el_paquete_no_rompe_el_menu(monkeypatch):
    """Si dos comandos acaban con el mismo nombre, Telegram rechaza la lista entera."""
    from src import locales
    roto = dict(locales.STRINGS["es"])
    roto["cmd.name.alertas"] = "stats"  # choca con /stats
    monkeypatch.setitem(locales.STRINGS, "xx", roto)
    nombres = [c.command for c in gc._menu_commands(gc._ADMIN_MENU, "xx")]
    assert len(nombres) == len(set(nombres))
    assert "alertas" in nombres  # cayó al nombre por defecto


def test_comando_sin_clave_de_nombre_usa_el_por_defecto():
    """`t()` devuelve la clave cruda si no existe; no debe colarse en el menú."""
    assert gc._menu_name("ban", "en") == "ban"
    assert gc._menu_name("stats", "es") == "stats"
