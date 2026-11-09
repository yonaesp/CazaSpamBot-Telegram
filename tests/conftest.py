"""Fixtures pytest comunes."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Permitir `from src...` desde tests sin instalar paquete
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Las que fijan el repositorio (`git rev-parse --local-env-vars`). El pre-commit de un
# worktree las exporta con ruta absoluta, y el `git init` de test_update_sh reescribió
# el .git/config de verdad: bare = true y la identidad de commit «t <t@t>» (L60).
for _var in ("GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS",
             "GIT_CONFIG_COUNT", "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE",
             "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE", "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS",
             "GIT_REPLACE_REF_BASE", "GIT_PREFIX", "GIT_SHALLOW_FILE", "GIT_COMMON_DIR"):
    os.environ.pop(_var, None)


@pytest.fixture
def tmp_db(tmp_path):
    from src.db import DB
    db = DB(str(tmp_path / "test.db"))
    yield db
    db.close()


@pytest.fixture(autouse=True)
def _reset_i18n():
    """El idioma de i18n es global; tras cada test se resetea a 'es' para aislarlos."""
    yield
    from src import i18n
    i18n.set_lang("es")
