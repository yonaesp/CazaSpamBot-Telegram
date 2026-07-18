"""Meta-test del gotcha documentado en CLAUDE.md: `sqlite3.Row` NO tiene `.get()`.

Regresión real (2026-07-16): `cmd_ban` y `cmd_spam` usaban `chat_row.get("chat_id")`
dentro del `except` del admin-guard. Cuando `get_chat_member` fallaba de verdad
(BadRequest: Participant_id_invalid, usuario que no está en ese chat), la propia
línea de log petaba con AttributeError, la excepción escapaba de `cmd_ban` y el
baneo NO llegaba a ejecutarse (parecía que sí, pero no se baneaba a nadie).

Este test escanea el código en busca de `.get(` sobre variables que en este proyecto
son siempre filas de SQLite, para que no vuelva a colarse en ningún módulo.
"""
from __future__ import annotations

import glob
import re

# Variables que SIEMPRE son sqlite3.Row en src/ (vienen de los helpers de db).
# OJO: `row` a secas iba fuera en la primera versión de este test — justo el nombre
# más probable. El bug original fue `chat_row.get()`; un `row.get()` idéntico se
# habría colado por el agujero del propio guard. NO incluir `pending` (es un dict
# real: context.user_data en config_panel).
_ROW_PATTERNS = (
    r"\brow\.get\(",       # el nombre más obvio
    r"\b\w+_row\.get\(",   # chat_row, seen_row, action_row, ...
    r"\bseen\.get\(",      # db.get_seen(...) → Row
    r"\bsettings\.get\(",  # db.get_chat_settings(...) → Row
)


def test_ningun_get_sobre_sqlite_row():
    offenders: list[str] = []
    for path in glob.glob("src/**/*.py", recursive=True):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for pat in _ROW_PATTERNS:
            for m in re.finditer(pat, src):
                line = src[: m.start()].count("\n") + 1
                offenders.append(f"{path}:{line} → {m.group(0)}")
    assert not offenders, (
        'sqlite3.Row no tiene .get(): usa row["columna"] (la columna existe; `or` '
        "maneja el NULL). Encontrado en:\n  " + "\n  ".join(offenders)
    )
