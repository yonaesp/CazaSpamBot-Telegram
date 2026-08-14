"""Un comando sin permiso no puede parecer una avería.

Reportado por un admin real (11-ago-2026): «he usado /warn, el mensaje se borra
pero no pone el warn». No había ningún bug. Eran dos comportamientos correctos
por separado que juntos engañan:

1. `group_clean.on_group_command_message` borra en los grupos CUALQUIER mensaje
   que invoque un comando del bot, sin mirar quién lo escribe.
2. `cmd_warn` lleva `@bot_admin_only`, cuyo docstring decía «Otros se ignoran
   silenciosamente».

Resultado desde fuera: escribes `/warn`, tu mensaje desaparece —como si el bot lo
hubiera procesado— y no pasa nada. Indistinguible de un bot roto, y encima el
admin se queda pensando que el warn está puesto cuando no lo está.

El arreglo NO es dar permisos (eso es una decisión del dueño del bot, y con la
federación un warn puede acabar en un ban en los cuatro grupos): es que el
silencio deje de mentir.
"""
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from src import permissions


class _Bot:
    def __init__(self):
        self.enviados = []

    async def send_message(self, chat_id, text, **kw):
        self.enviados.append((chat_id, text))
        return NS(message_id=999)


def _update(user_id):
    return NS(
        effective_user=NS(id=user_id, username="quien", first_name="Quien"),
        effective_message=NS(chat_id=-100, message_id=5),
    )


def _ctx(bot, admin_id=1, es_admin_de_grupo=True):
    ctx = NS(
        bot=bot,
        bot_data={"cfg": NS(admin_user_id=admin_id), "db": None},
        application=NS(job_queue=None),
    )
    return ctx


@pytest.fixture(autouse=True)
def _sin_consultar_a_telegram(monkeypatch):
    """`is_chat_admin_any` habla con la API; aquí se controla a mano."""
    async def falso(context, user_id):
        return context.bot_data.get("_es_admin_de_grupo", True)
    monkeypatch.setattr(permissions, "is_chat_admin_any", falso)


@pytest.mark.asyncio
async def test_al_admin_de_grupo_se_le_dice_que_no_se_aplico_nada():
    bot = _Bot()
    ctx = _ctx(bot)
    llamado = []

    @permissions.bot_admin_only
    async def cmd(update, context):
        llamado.append(1)

    await cmd(_update(555), ctx)               # no es el admin del bot
    assert not llamado, "no puede ejecutarse el comando"
    assert bot.enviados, "el silencio es indistinguible de una avería"
    assert "no se ha aplicado nada" in bot.enviados[0][1]


@pytest.mark.asyncio
async def test_al_usuario_normal_se_le_sigue_ignorando():
    """Contestarle sería enseñarle qué comandos existen."""
    bot = _Bot()
    ctx = _ctx(bot)
    ctx.bot_data["_es_admin_de_grupo"] = False

    @permissions.bot_admin_only
    async def cmd(update, context):
        pass

    await cmd(_update(777), ctx)
    assert not bot.enviados


@pytest.mark.asyncio
async def test_el_admin_del_bot_ejecuta_sin_aviso():
    bot = _Bot()
    ctx = _ctx(bot, admin_id=1)
    llamado = []

    @permissions.bot_admin_only
    async def cmd(update, context):
        llamado.append(1)

    await cmd(_update(1), ctx)
    assert llamado == [1]
    assert not bot.enviados


@pytest.mark.asyncio
async def test_no_se_repite_el_aviso_a_cada_comando():
    """Un admin que insiste ya lo ha leído; repetírselo es ensuciar el grupo."""
    bot = _Bot()
    ctx = _ctx(bot)

    @permissions.bot_admin_only
    async def cmd(update, context):
        pass

    for _ in range(5):
        await cmd(_update(555), ctx)
    assert len(bot.enviados) == 1


@pytest.mark.asyncio
async def test_pasado_el_rato_se_le_vuelve_a_decir():
    bot = _Bot()
    ctx = _ctx(bot)

    @permissions.bot_admin_only
    async def cmd(update, context):
        pass

    await cmd(_update(555), ctx)
    ctx.bot_data["_aviso_sin_permiso"][(-100, 555)] = time.time() - permissions._AVISO_CADA_S - 1
    await cmd(_update(555), ctx)
    assert len(bot.enviados) == 2


@pytest.mark.asyncio
async def test_si_no_se_puede_avisar_no_revienta_el_comando():
    """El aviso es cosmético: jamás puede romper la ruta de un comando."""
    class Rota:
        async def send_message(self, *a, **k):
            from telegram.error import TelegramError
            raise TelegramError("sin permiso para escribir")

    @permissions.bot_admin_only
    async def cmd(update, context):
        pass

    await cmd(_update(555), _ctx(Rota()))      # no debe lanzar


def test_el_aviso_se_borra_solo():
    """Es un aviso, no un cartel: el grupo tiene que quedar limpio."""
    fuente = Path("src/permissions.py").read_text()
    assert "borrado_diferido.programar" in fuente
    assert permissions._AVISO_TTL_S <= 120


def test_el_docstring_ya_no_promete_silencio():
    """El texto viejo («Otros se ignoran silenciosamente») describía justo el
    comportamiento que confundió al admin."""
    doc = permissions.bot_admin_only.__doc__ or ""
    assert "silenciosamente" not in doc


def test_los_comandos_que_modifican_siguen_siendo_del_admin_del_bot():
    """El aviso NO abre la mano: quién puede warnear no cambia. Con la federación,
    un warn puede acabar en un ban en los cuatro grupos, así que ampliar esto es
    una decisión del dueño del bot, no un efecto secundario."""
    fuente = Path("src/warns_mod.py").read_text()
    i = fuente.index("async def cmd_warn(")
    assert "@_admin_only" in fuente[max(0, i - 200):i]
