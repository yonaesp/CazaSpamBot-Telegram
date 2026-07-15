"""Fixtures pytest comunes."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Permitir `from src...` desde tests sin instalar paquete
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
