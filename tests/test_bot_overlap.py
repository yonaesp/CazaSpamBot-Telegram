"""Aviso de otro bot ADMIN en el grupo (`maintenance.notify_bot_overlap`).

Nace del caso real de @MissRose_bot: un bot de moderación legítimo y con permisos de
admin conviviendo con el nuestro. No hay forma de saber qué hace ese bot, así que el
aviso solo dice que PUEDE solaparse (bienvenida, verificación, warns) y ofrece apagar
lo nuestro en /config.

Lo que se protege aquí:
  - se avisa UNA vez por pareja chat+bot (si no, cada noche repite y acaba silenciado);
  - un fallo de Telegram nunca aborta el mantenimiento ni pierde el aviso;
  - no se avisa por uno mismo ni por administradores humanos.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import TelegramError

from src import maintenance

CHAT = -1001234567890
NOTIFY_CHAT = 555
ADMIN = 777


def _bot_member(uid: int, nombre: str, usuario: str | None = None, es_bot: bool = True):
    return SimpleNamespace(user=SimpleNamespace(
        id=uid, is_bot=es_bot, first_name=nombre, username=usuario))


def _mk(tmp_path, admins, *, titulo="Domótica", notify_chat=NOTIFY_CHAT, fallo_envio=False):
    """Context falso + DB real con un grupo donde el bot es admin."""
    from src.db import DB
    db = DB(str(tmp_path / "overlap.db"))
    db.upsert_bot_chat(CHAT, titulo, "supergroup", True, True, True)

    enviados: list[dict] = []

    async def _send(chat_id, text, **kw):
        if fallo_envio:
            raise TelegramError("bot was blocked by the user")
        enviados.append({"chat_id": chat_id, "text": text, "kb": kw.get("reply_markup")})
        return SimpleNamespace(message_id=len(enviados))

    async def _admins(chat_id):
        if isinstance(admins, Exception):
            raise admins
        return admins

    bot = SimpleNamespace(
        id=100, send_message=AsyncMock(side_effect=_send),
        get_chat_administrators=AsyncMock(side_effect=_admins),
    )
    cfg = SimpleNamespace(admin_notify_chat_id=notify_chat, admin_user_id=ADMIN)
    ctx = SimpleNamespace(bot=bot, bot_data={"db": db, "cfg": cfg})
    return ctx, db, enviados


@pytest.mark.asyncio
async def test_avisa_del_otro_bot_admin(tmp_path):
    ctx, db, enviados = _mk(tmp_path, [_bot_member(200, "Rose", "MissRose_bot")])
    assert await maintenance.notify_bot_overlap(ctx) == 1
    assert len(enviados) == 1
    assert enviados[0]["chat_id"] == NOTIFY_CHAT
    texto = enviados[0]["text"]
    assert "Rose" in texto and "@MissRose_bot" in texto
    assert "Domótica" in texto and str(CHAT) in texto


@pytest.mark.asyncio
async def test_no_repite_en_la_siguiente_pasada(tmp_path):
    """Sin dedupe el aviso saldría cada noche y el admin lo silenciaría por hartazgo."""
    ctx, db, enviados = _mk(tmp_path, [_bot_member(200, "Rose", "MissRose_bot")])
    assert await maintenance.notify_bot_overlap(ctx) == 1
    assert await maintenance.notify_bot_overlap(ctx) == 0
    assert await maintenance.notify_bot_overlap(ctx) == 0
    assert len(enviados) == 1


@pytest.mark.asyncio
async def test_bot_nuevo_en_el_mismo_chat_si_avisa(tmp_path):
    """La marca es por pareja chat+bot: otro bot distinto merece su propio aviso."""
    admins = [_bot_member(200, "Rose", "MissRose_bot")]
    ctx, db, enviados = _mk(tmp_path, admins)
    await maintenance.notify_bot_overlap(ctx)
    admins.append(_bot_member(300, "Combot", "combot"))
    assert await maintenance.notify_bot_overlap(ctx) == 1
    assert "Combot" in enviados[-1]["text"]


@pytest.mark.asyncio
async def test_respeta_el_silenciado(tmp_path):
    ctx, db, enviados = _mk(tmp_path, [_bot_member(200, "Rose", "MissRose_bot")])
    db.set_pref("notify_bot_overlap", False)  # botón 🔕 del propio aviso o /alertas
    assert await maintenance.notify_bot_overlap(ctx) == 0
    assert enviados == []
    ctx.bot.get_chat_administrators.assert_not_called()  # ni gasta la llamada


@pytest.mark.asyncio
async def test_no_avisa_si_el_unico_bot_admin_soy_yo(tmp_path):
    ctx, db, enviados = _mk(tmp_path, [_bot_member(100, "CazaSpamBot", "CazaSpamBot")])
    assert await maintenance.notify_bot_overlap(ctx) == 0
    assert enviados == []


@pytest.mark.asyncio
async def test_los_admins_humanos_no_cuentan(tmp_path):
    ctx, db, enviados = _mk(tmp_path, [
        _bot_member(ADMIN, "Jonatan", "YonaPN", es_bot=False),
        _bot_member(900, "Otro humano", None, es_bot=False),
    ])
    assert await maintenance.notify_bot_overlap(ctx) == 0
    assert enviados == []


@pytest.mark.asyncio
async def test_fallo_de_get_chat_administrators_no_rompe(tmp_path):
    """El bot puede haber perdido admin o Telegram devolver 5xx: se sigue."""
    ctx, db, enviados = _mk(tmp_path, TelegramError("chat not found"))
    assert await maintenance.notify_bot_overlap(ctx) == 0
    assert enviados == []


@pytest.mark.asyncio
async def test_si_falla_el_envio_no_marca_y_reintenta(tmp_path):
    """Marcar antes de que salga el mensaje dejaría al admin sin enterarse nunca."""
    admins = [_bot_member(200, "Rose", "MissRose_bot")]
    ctx, db, _ = _mk(tmp_path, admins, fallo_envio=True)
    assert await maintenance.notify_bot_overlap(ctx) == 0
    assert db.get_pref(maintenance._overlap_key(CHAT, 200)) is None

    ctx2, db2, enviados2 = _mk(tmp_path, admins)  # misma BD, ya sin fallo de envío
    assert await maintenance.notify_bot_overlap(ctx2) == 1
    assert len(enviados2) == 1


@pytest.mark.asyncio
async def test_sin_chat_de_avisos_va_al_dm_del_admin(tmp_path):
    ctx, db, enviados = _mk(tmp_path, [_bot_member(200, "Rose", "MissRose_bot")],
                            notify_chat=0)
    assert await maintenance.notify_bot_overlap(ctx) == 1
    assert enviados[0]["chat_id"] == ADMIN


@pytest.mark.asyncio
async def test_sin_admin_configurado_no_manda_nada(tmp_path):
    ctx, db, enviados = _mk(tmp_path, [_bot_member(200, "Rose", "MissRose_bot")],
                            notify_chat=0)
    ctx.bot_data["cfg"] = SimpleNamespace(admin_notify_chat_id=0, admin_user_id=0)
    assert await maintenance.notify_bot_overlap(ctx) == 0
    assert enviados == []


@pytest.mark.asyncio
async def test_solo_grupos_donde_soy_admin(tmp_path):
    """En un grupo donde no soy admin no puedo moderar: nada que solapar."""
    ctx, db, enviados = _mk(tmp_path, [_bot_member(200, "Rose", "MissRose_bot")])
    db.upsert_bot_chat(-100999, "Grupo sin permisos", "supergroup", False, False, False)
    await maintenance.notify_bot_overlap(ctx)
    assert ctx.bot.get_chat_administrators.call_count == 1


@pytest.mark.asyncio
async def test_texto_completo_sin_placeholders_ni_html_roto(tmp_path):
    """Telegram rechaza el mensaje ENTERO si un <b> queda abierto, y el aviso se
    perdería en silencio. Un {placeholder} visible es un texto roto."""
    ctx, db, enviados = _mk(tmp_path, [_bot_member(200, "Rose", "MissRose_bot")])
    await maintenance.notify_bot_overlap(ctx)
    texto = enviados[0]["text"]
    assert "{" not in texto and "}" not in texto
    for tag in ("b", "i", "code"):
        assert len(re.findall(rf"<{tag}(?:\s[^>]*)?>", texto)) == len(
            re.findall(rf"</{tag}>", texto)), f"<{tag}> desbalanceado"
    assert "—" not in texto  # sin em dashes en textos visibles
    # Lo que el admin necesita saber sin preguntar (caso Rose):
    assert "/config" in texto
    assert "banearlo" in texto and "botones" in texto


@pytest.mark.asyncio
async def test_escapa_el_nombre_del_otro_bot(tmp_path):
    """Nombre y @usuario vienen de datos externos: sin escapar, un '<' rompe el HTML."""
    ctx, db, enviados = _mk(tmp_path, [_bot_member(200, "<b>Rose</b>", "a_b_c")])
    await maintenance.notify_bot_overlap(ctx)
    texto = enviados[0]["text"]
    assert "&lt;b&gt;Rose&lt;/b&gt;" in texto
    assert "<b>Rose</b>" not in texto


@pytest.mark.asyncio
async def test_bot_sin_username_no_deja_arroba_huerfana(tmp_path):
    ctx, db, enviados = _mk(tmp_path, [_bot_member(200, "SinAlias", None)])
    assert await maintenance.notify_bot_overlap(ctx) == 1
    assert "(@" not in enviados[0]["text"]


@pytest.mark.asyncio
async def test_botones_del_aviso(tmp_path):
    """Silenciar + abrir los ajustes de ESE grupo, con el tope de 64 BYTES."""
    ctx, db, enviados = _mk(tmp_path, [_bot_member(200, "Rose", "MissRose_bot")])
    await maintenance.notify_bot_overlap(ctx)
    datos = [b.callback_data for fila in enviados[0]["kb"].inline_keyboard for b in fila]
    assert f"cfg:open:{CHAT}" in datos
    assert "npref:off:bot_overlap" in datos
    for d in datos:
        assert len(d.encode()) <= 64, d


def test_sale_en_el_panel_de_alertas():
    """El panel itera NOTIFY_TYPES, así que el tipo nuevo se puede silenciar sin
    tocar el panel. Y su etiqueta debe estar traducida (t() devuelve la clave si no)."""
    from src import notify_prefs
    assert "bot_overlap" in notify_prefs.NOTIFY_TYPES
    assert notify_prefs.label("bot_overlap") != "notify.bot_overlap"
    assert notify_prefs.default_for("bot_overlap", None) is True  # activo de fábrica


@pytest.mark.asyncio
async def test_el_job_nocturno_no_aborta_si_el_aviso_explota(tmp_path, monkeypatch):
    """Es un aviso informativo: no puede tumbar la limpieza ni la reconciliación."""
    ctx, db, _ = _mk(tmp_path, [_bot_member(200, "Rose", "MissRose_bot")])

    async def _boom(_ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(maintenance, "notify_bot_overlap", _boom)
    await maintenance.cleanup_nightly_job(ctx)  # no debe propagar


@pytest.mark.asyncio
async def test_el_job_nocturno_lo_llama(tmp_path):
    ctx, db, enviados = _mk(tmp_path, [_bot_member(200, "Rose", "MissRose_bot")])
    await maintenance.cleanup_nightly_job(ctx)
    assert len(enviados) == 1


# ---------------------------------------------------------------------------
# El aviso llevaba desde siempre sin avisar
#
# Encontrado el 2026-08-21 investigando por qué `@noarab_bot` baneaba en Windows
# 10 sin que el admin hubiera recibido nunca un aviso de solape.
#
# `getChatAdministrators` devuelve la lista de admins **excluyendo a los demás
# bots**, que es justo lo único que este aviso busca. Medido en los cuatro grupos
# reales: sin `return_bots` → 0 bots; con él → 7 (AlexaESPAli_bot,
# AlexaDomoChollosBot, noarab_bot, xxdamage2bot…). El parámetro llegó con Bot API
# 10.0, así que hasta entonces esto era inviable: la función corría cada noche,
# recorría los grupos y no encontraba nada. Cero avisos, cero logs.
#
# Los tests de arriba pasaban porque sus dobles devolvían bots sin filtrar, que
# NO es lo que hace Telegram. De ahí el doble de abajo.
# ---------------------------------------------------------------------------

def test_se_piden_los_bots_explicitamente():
    """La costura del arreglo: si alguien quita esto, el aviso vuelve a ser mudo."""
    from pathlib import Path
    fuente = Path("src/maintenance.py").read_text()
    i = fuente.index("async def notify_bot_overlap(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    assert "return_bots" in cuerpo


def test_el_soporte_se_mira_por_firma_no_con_un_except():
    """Un `except TypeError` alrededor de la llamada se tragaría también un error
    de tipos de verdad, y volveríamos a tener la función muda sin enterarnos."""
    from pathlib import Path
    fuente = Path("src/maintenance.py").read_text()
    i = fuente.index("async def notify_bot_overlap(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    assert "inspect.signature" in cuerpo
    assert "except TypeError:" not in cuerpo


@pytest.mark.asyncio
async def test_con_un_telegram_que_filtra_bots_como_el_real(tmp_path):
    """El doble se comporta como Telegram DE VERDAD: sin `return_bots` no
    devuelve otros bots. Con el código anterior, este test daría 0 avisos."""
    vistos = []

    class _BotQueFiltra:
        id = 1

        async def get_chat_administrators(self, chat_id, return_bots=False):
            # Firma REAL, no un AsyncMock: así `inspect.signature` ve el
            # parámetro y el código bajo prueba lo usa de verdad.
            humanos = [SimpleNamespace(
                user=SimpleNamespace(id=99, is_bot=False, first_name="Ana", username="ana"))]
            if not return_bots:
                return humanos
            return humanos + [SimpleNamespace(
                user=SimpleNamespace(id=2, is_bot=True, first_name="NoArab",
                                     username="noarab_bot"))]

        async def send_message(self, chat_id, text, **kw):
            vistos.append(text)
            return SimpleNamespace(message_id=1)

    from src.db import DB
    db = DB(str(tmp_path / "filtra.db"))
    db.upsert_bot_chat(CHAT, "Windows 10", "supergroup", True, True, True)
    cfg = SimpleNamespace(admin_notify_chat_id=NOTIFY_CHAT, admin_user_id=ADMIN)
    ctx = SimpleNamespace(bot=_BotQueFiltra(), bot_data={"db": db, "cfg": cfg})

    assert await maintenance.notify_bot_overlap(ctx) == 1, (
        "con un Telegram que filtra bots (el real), el aviso no encontró nada")
    assert "NoArab" in vistos[0]
