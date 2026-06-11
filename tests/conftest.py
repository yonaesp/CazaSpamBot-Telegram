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
