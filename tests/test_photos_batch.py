"""Tests del detector photos_batch_upload (fotos en ráfaga)."""
from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.detectors import photos_batch as det


def _photo(seconds_ago: float, photo_id: int = 1):
    """Photo con .date timezone-aware."""
    return SimpleNamespace(
        date=_dt.datetime.fromtimestamp(_dt.datetime.now().timestamp() - seconds_ago, tz=_dt.timezone.utc),
        id=photo_id,
    )


@pytest.mark.asyncio
async def test_no_client_returns_none():
    hit = await det.check(None, user_id=123)
    assert hit is None or hit.score == 0


@pytest.mark.asyncio
async def test_no_photos_returns_none():
    client = MagicMock()
    client.get_entity = AsyncMock(return_value=SimpleNamespace(id=123))
    client.get_profile_photos = AsyncMock(return_value=[])
    hit = await det.check(client, user_id=123)
    assert hit is None or hit.score == 0


@pytest.mark.asyncio
async def test_less_than_min_photos():
    client = MagicMock()
    client.get_entity = AsyncMock(return_value=SimpleNamespace(id=123))
    client.get_profile_photos = AsyncMock(return_value=[_photo(0, 1), _photo(5, 2)])
    hit = await det.check(client, user_id=123)
    assert hit is None or hit.score == 0


@pytest.mark.asyncio
async def test_5_photos_in_18_seconds_triggers():
    """Caso Javier: 5 fotos en 18 segundos → ban."""
    photos = [_photo(0, 1), _photo(3, 2), _photo(8, 3), _photo(13, 4), _photo(18, 5)]
    client = MagicMock()
    client.get_entity = AsyncMock(return_value=SimpleNamespace(id=123))
    client.get_profile_photos = AsyncMock(return_value=photos)
    hit = await det.check(client, user_id=123)
    assert hit is not None
    assert hit.rule == "photos_batch_upload"
    assert hit.score == 100
    assert hit.payload["n_photos"] == 5
    assert hit.payload["span_seconds"] < 120


@pytest.mark.asyncio
async def test_photos_spread_over_days_no_trigger():
    """Usuario legítimo: fotos espaciadas en días."""
    photos = [_photo(0, 1), _photo(86400, 2), _photo(172800, 3)]
    client = MagicMock()
    client.get_entity = AsyncMock(return_value=SimpleNamespace(id=123))
    client.get_profile_photos = AsyncMock(return_value=photos)
    hit = await det.check(client, user_id=123)
    assert hit is None or hit.score == 0


@pytest.mark.asyncio
async def test_fallback_to_username_if_id_fails():
    """Si get_entity por id falla, intentar con @username."""
    photos = [_photo(0, 1), _photo(10, 2), _photo(20, 3)]
    client = MagicMock()
    client.get_entity = AsyncMock(side_effect=[
        Exception("id not found"),
        SimpleNamespace(id=123),
    ])
    client.get_profile_photos = AsyncMock(return_value=photos)
    hit = await det.check(client, user_id=123, username="someuser")
    assert hit is not None
    assert hit.score == 100


@pytest.mark.asyncio
async def test_3_photos_in_2min_boundary():
    """Caso límite: 3 fotos en exactamente 120s → debe disparar (≤120)."""
    photos = [_photo(0, 1), _photo(60, 2), _photo(119, 3)]
    client = MagicMock()
    client.get_entity = AsyncMock(return_value=SimpleNamespace(id=123))
    client.get_profile_photos = AsyncMock(return_value=photos)
    hit = await det.check(client, user_id=123)
    assert hit is not None
    assert hit.score == 100


@pytest.mark.asyncio
async def test_bypass_cuenta_antigua():
    """Fotos en batch pero la más antigua tiene >1 año → cuenta vieja, NO ban.
    Un user real pudo subir su galería de golpe hace años."""
    DAY = 86400
    base = 400 * DAY  # ~1.1 años atrás
    photos = [
        _photo(base, 1), _photo(base - 5, 2), _photo(base - 10, 3),
        _photo(base - 15, 4), _photo(base - 18, 5),
    ]
    client = MagicMock()
    client.get_entity = AsyncMock(return_value=SimpleNamespace(id=123))
    client.get_profile_photos = AsyncMock(return_value=photos)
    hit = await det.check(client, user_id=123)
    assert hit is None or hit.score == 0
