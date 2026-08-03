"""Ningún mute puede devolver al grupo a alguien expulsado.

En Telegram, `restrictChatMember` sobre alguien EXPULSADO **lo devuelve al grupo**
como restringido: pasa de estar fuera a estar dentro y callado, y el registro
sigue diciendo que está baneado. Es exactamente la transición que costó día y
medio detectar en agosto de 2026.

Allí la provocó la app de Telegram, no el bot. Pero al auditarlo aparecieron
CUATRO sitios del bot que podían hacer lo mismo sin comprobar nada: el botón SOY
HUMANO, el mute del antiflood, el de la acción de moderación y el provisional al
entrar.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import verification as v


class _DB:
    def __init__(self, baneado):
        self._b = baneado

    def is_banned(self, _uid):
        return self._b


@pytest.mark.asyncio
async def test_no_restringe_a_un_baneado():
    bot = MagicMock()
    bot.restrict_chat_member = AsyncMock()
    ok = await v.restringir_seguro(bot, _DB(True), -100, 777, "perms", "prueba")
    assert ok is False
    assert bot.restrict_chat_member.await_count == 0, (
        "aplicó permisos a un baneado: lo habría devuelto al grupo")


@pytest.mark.asyncio
async def test_si_no_esta_baneado_restringe_normal():
    bot = MagicMock()
    bot.restrict_chat_member = AsyncMock()
    ok = await v.restringir_seguro(bot, _DB(False), -100, 777, "perms", "prueba")
    assert ok is True
    assert bot.restrict_chat_member.await_count == 1


@pytest.mark.asyncio
async def test_conserva_la_duracion_del_mute():
    """Sin `until_date`, un mute temporal (antiflood 24 h) se volvería permanente
    y nadie lo notaría hasta que el usuario se quejara días después."""
    bot = MagicMock()
    bot.restrict_chat_member = AsyncMock()
    await v.restringir_seguro(bot, _DB(False), -100, 777, "perms", "x", until_date=12345)
    assert bot.restrict_chat_member.await_args.kwargs["until_date"] == 12345


@pytest.mark.asyncio
async def test_un_fallo_al_consultar_no_impide_restringir():
    """Si la consulta del ban peta, se sigue adelante: el mute es lo importante."""
    class _Roto:
        def is_banned(self, _uid):
            raise RuntimeError("BD ocupada")
    bot = MagicMock()
    bot.restrict_chat_member = AsyncMock()
    assert await v.restringir_seguro(bot, _Roto(), -100, 777, "perms") is True


def test_los_cuatro_sitios_usan_el_helper():
    from pathlib import Path
    verif = Path("src/verification.py").read_text()
    hand = Path("src/handlers.py").read_text()
    assert "restringir_seguro(context.bot, db, chat_id, target_user_id" in verif, (
        "el botón SOY HUMANO no está protegido: un baneado con la verificación "
        "pendiente volvería al grupo al pulsarlo")
    assert hand.count("restringir_seguro") >= 2, (
        "faltan sitios de handlers por proteger (antiflood y acción mute)")
