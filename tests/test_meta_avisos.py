"""Meta-tests: la clase de fallo de L55, en todo `src/`.

El aviso del ban de «Chelsea» (7-nov-2026) no llegó porque (1) la limpieza de
`federate_ban` borró el mensaje antes de copiarlo y (2) la copia y el aviso iban en el
mismo `try`: la copia fallida se llevó el aviso. Los tests de entonces no lo veían
porque sus dobles copiaban cualquier cosa. Estos miran la estructura con `ast`.
"""
from __future__ import annotations

import ast
from pathlib import Path

FUENTES = sorted(Path("src").rglob("*.py"))


def _llamadas(nodo: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(nodo) if isinstance(n, ast.Call)]


def _llamadas_directas(nodo: ast.AST) -> list[ast.Call]:
    """Las llamadas de `nodo` sin entrar en otro `try` ni en otra función: lo que
    protege su propio `try` no cuenta para el de fuera."""
    if isinstance(nodo, (ast.Try, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return []
    propias = [nodo] if isinstance(nodo, ast.Call) else []
    for hijo in ast.iter_child_nodes(nodo):
        propias += _llamadas_directas(hijo)
    return propias


def _nombre(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def _funciones(arbol: ast.AST):
    return [n for n in ast.walk(arbol) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def test_ningun_aviso_depende_de_que_salga_la_copia():
    """Un `try` que copia un mensaje y además manda texto: si la copia falla, el texto
    no sale. Cada envío, en su `try`."""
    malos = []
    for f in FUENTES:
        for t in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not isinstance(t, ast.Try):
                continue
            nombres = [_nombre(c) for st in t.body for c in _llamadas_directas(st)]
            if "copy_message" in nombres and "send_message" in nombres:
                malos.append(f"{f}:{t.lineno}")
    assert not malos, f"copia y aviso en el mismo try (L55): {malos}"


def test_quien_banea_y_luego_copia_conserva_el_mensaje():
    """`federate_ban` retira los mensajes del baneado: si la función copia después el
    mensaje al aviso, tiene que pasarle `conservar=`."""
    malos = []
    for f in FUENTES:
        for fn in _funciones(ast.parse(f.read_text(encoding="utf-8"))):
            llamadas = _llamadas(fn)
            copias = [c.lineno for c in llamadas if _nombre(c) == "copy_message"]
            for c in llamadas:
                if _nombre(c) != "federate_ban" or not any(n > c.lineno for n in copias):
                    continue
                if not any(k.arg == "conservar" for k in c.keywords):
                    malos.append(f"{f}:{c.lineno} ({fn.name})")
    assert not malos, f"federate_ban antes de copiar sin conservar= (L55): {malos}"


def test_el_aviso_de_accion_no_dice_sincronizado_a_ciegas():
    """«Sincronizado en todos los grupos» solo si de verdad se federó (`_se_federa`)."""
    src = Path("src/handlers.py").read_text(encoding="utf-8")
    for clave in ('t("hdl.act.ban")', 't("hdl.would.ban")'):
        for linea in [x for x in src.splitlines() if clave in x]:
            assert "_se_federa(" in linea, f"{clave} sin mirar si se federó: {linea.strip()}"
