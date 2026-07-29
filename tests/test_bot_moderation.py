"""Moderación de mensajes de BOTS miembros del grupo.

Caso real (2026-07-30): el bot expulsó a @MissRose_bot de los 4 grupos por
publicar su aviso de warn, que lleva un botón inline. Rose llevaba 685 mensajes
legítimos en ese grupo. El detector de botones existe porque un HUMANO no puede
crear botones (si aparecen, reenvió algo de un canal promocional), pero en un BOT
los botones son su forma normal de trabajar, así que ahí no prueban nada.
"""
import ast
import inspect

import pytest
from telegram.error import TelegramError

from src import handlers


def test_la_ruta_de_bots_no_usa_el_detector_de_botones():
    """Comprobado por AST y no por texto: el nombre aparece en un comentario."""
    arbol = ast.parse(inspect.getsource(handlers._moderate_bot_message).lstrip())
    llamadas = {
        f"{n.func.value.id}.{n.func.attr}"
        for n in ast.walk(arbol)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
    }
    assert "buttons_det.check" not in llamadas, "un bot con botones volvería a ser baneado"


def test_la_ruta_de_bots_sigue_mirando_spam_real():
    """Quitar los botones no puede dejar la ruta sin dientes: un bot que suelta
    una URL de la lista negra o un anuncio estructurado sigue cayendo."""
    arbol = ast.parse(inspect.getsource(handlers._moderate_bot_message).lstrip())
    llamadas = {
        f"{n.func.value.id}.{n.func.attr}"
        for n in ast.walk(arbol)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
    }
    assert "url_det.check" in llamadas
    assert "comad_det.check" in llamadas


def test_el_detector_de_botones_sigue_activo_para_humanos():
    """El detector no se ha tocado: sigue siendo válido cuando el emisor es humano."""
    from types import SimpleNamespace as NS

    from src.detectors import inline_buttons as bd
    msg = NS(text="mira esta oferta", caption=None, entities=[], caption_entities=[],
             reply_markup=NS(inline_keyboard=[[NS(text="ENTRAR")]]))
    assert bd.check(msg).score > 0


@pytest.mark.asyncio
async def test_guarda_de_admins_falla_del_lado_seguro():
    """Si no se puede comprobar si es admin, se asume que SÍ y no se actúa.

    Antes devolvía False: un fallo transitorio de red bastaba para que la guarda
    dejara de proteger y se baneara a un administrador. Un spammer se caza en su
    siguiente mensaje; un admin baneado no se arregla solo.
    """
    from unittest.mock import AsyncMock, MagicMock
    ctx = MagicMock()
    ctx.bot_data = {}
    ctx.bot.get_chat_member = AsyncMock(side_effect=TelegramError("red caída"))
    assert await handlers._is_admin_of_chat(ctx, -100, 555) is True


@pytest.mark.asyncio
async def test_un_miembro_normal_sigue_siendo_baneable():
    from types import SimpleNamespace as NS
    from unittest.mock import AsyncMock, MagicMock
    ctx = MagicMock()
    ctx.bot_data = {}
    ctx.bot.get_chat_member = AsyncMock(return_value=NS(status="member"))
    assert await handlers._is_admin_of_chat(ctx, -100, 555) is False


@pytest.mark.asyncio
async def test_el_fallo_no_se_cachea():
    """Un fallo transitorio no puede dejar a alguien marcado como admin 5 minutos:
    la próxima comprobación debe reintentar de verdad."""
    from types import SimpleNamespace as NS
    from unittest.mock import AsyncMock, MagicMock
    ctx = MagicMock()
    ctx.bot_data = {}
    ctx.bot.get_chat_member = AsyncMock(side_effect=TelegramError("caída"))
    assert await handlers._is_admin_of_chat(ctx, -100, 777) is True
    # ahora la consulta funciona: debe volver a preguntar, no servir el fallo cacheado
    ctx.bot.get_chat_member = AsyncMock(return_value=NS(status="member"))
    assert await handlers._is_admin_of_chat(ctx, -100, 777) is False
