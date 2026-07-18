"""Meta-test i18n: cada llamada `t("clave", ...)` debe cuadrar con su clave.

Nace de un bug real (2026-07-18): `t("lang.set", lang=want)` enlazaba `want` al
parámetro selector de idioma (que se llamaba `lang`) en vez de a `**fmt`, así que
`.format()` no se ejecutaba y el usuario veía literalmente «{lang}». No lanzaba
excepción ni salía en los logs: texto roto y silencioso.

Este test escanea el AST de `src/` y, para cada llamada con clave literal, verifica:
  1. la clave existe en los paquetes es y en;
  2. los placeholders del texto coinciden EXACTAMENTE con los kwargs pasados
     (ni de más → «{x}» visible, ni de menos → argumento ignorado).
El selector `_lang` se excluye por diseño (no es un placeholder).
"""
from __future__ import annotations

import ast
import glob
from string import Formatter

from src.locales import STRINGS


# Claves PLANTILLA: t() las devuelve a propósito sin formatear porque su {name}/{chat}
# lo sustituye después quien las envía (con el guard de llaves raras). Pedirles que
# cuadren con los kwargs de la llamada sería un falso positivo.
_PLANTILLAS = {
    "welcome.default",
    "welcome.clean_default",
    "welcome.friendly1",
    "welcome.friendly2",
}


def _placeholders(text: str) -> set[str]:
    """Nombres de placeholder de un texto ('{a} {b}' -> {'a','b'}); ignora {{escapados}}."""
    return {f for _, f, _, _ in Formatter().parse(text) if f}


def _t_calls(path: str):
    """(clave, kwargs, línea) de cada llamada t(...) / i18n.t(...) con clave literal."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name != "t" or not node.args:
            continue
        key_node = node.args[0]
        if not (isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)):
            continue  # clave dinámica: fuera del alcance de este test
        kwargs = {kw.arg for kw in node.keywords if kw.arg and kw.arg != "_lang"}
        yield key_node.value, kwargs, node.lineno


def test_llamadas_t_cuadran_con_sus_claves():
    problemas: list[str] = []
    for path in glob.glob("src/**/*.py", recursive=True):
        for key, kwargs, line in _t_calls(path):
            texto = STRINGS["es"].get(key)
            if texto is None:
                problemas.append(f"{path}:{line} → clave inexistente: {key!r}")
                continue
            if key in _PLANTILLAS:
                continue
            if key not in STRINGS["en"]:
                problemas.append(f"{path}:{line} → {key!r} no está en el paquete en")
                continue
            for lg in ("es", "en"):
                esperados = _placeholders(STRINGS[lg][key])
                if esperados != kwargs:
                    problemas.append(
                        f"{path}:{line} → {key!r} [{lg}] espera {sorted(esperados) or '—'} "
                        f"pero recibe {sorted(kwargs) or '—'}")
    assert not problemas, "Llamadas t() que no cuadran:\n  " + "\n  ".join(problemas)
