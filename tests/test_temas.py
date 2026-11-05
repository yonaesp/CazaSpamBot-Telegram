"""Grupos con temas (foros): respuesta real, tema donde publicar y el @admin.

Caso real (5-nov-2026, Domótica/Alexa, grupo con temas): un miembro escribió
«@admin» (451506) en General sin responder a nada. El bot supuso el mensaje 451505,
que era suyo y de OTRO tema, y el aviso enlazaba allí; el spam (451503, de un bot
invitado) estaba justo encima en General. Tres horas después el miembro editó el
@admin y el bot volvió a mandar el aviso, que llegó como si fuera nuevo.
"""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest

from src import admin_report, temas
from src.db import DB

CHAT, ADMIN_DM = -1001156069668, 345
TEMA_ECHO = 448581  # el tema donde estaba el 451505


# ------------------------------------------------------------------ temas.py

def test_en_un_tema_la_respuesta_falsa_al_mensaje_que_lo_creo_no_cuenta():
    from telegram import ForumTopicCreated
    inicio = NS(message_id=TEMA_ECHO, forum_topic_created=ForumTopicCreated(name="Echo", icon_color=0x6FB9F0),
                from_user=NS(id=1))
    msg = NS(is_topic_message=True, message_thread_id=TEMA_ECHO, reply_to_message=inicio)
    assert temas.respuesta(msg) is None


def test_aunque_no_traiga_forum_topic_created_si_es_el_inicio_del_tema_no_cuenta():
    msg = NS(is_topic_message=True, message_thread_id=TEMA_ECHO,
             reply_to_message=NS(message_id=TEMA_ECHO, forum_topic_created=None))
    assert temas.respuesta(msg) is None


def test_una_respuesta_de_verdad_dentro_de_un_tema_si_cuenta():
    r = NS(message_id=451400, forum_topic_created=None)
    msg = NS(is_topic_message=True, message_thread_id=TEMA_ECHO, reply_to_message=r)
    assert temas.respuesta(msg) is r


def test_en_un_grupo_normal_una_cadena_de_respuestas_no_es_un_tema():
    """PTB: `message_thread_id` también existe en un grupo normal (la cadena)."""
    r = NS(message_id=10, forum_topic_created=None)
    msg = NS(is_topic_message=False, message_thread_id=10, reply_to_message=r)
    assert temas.respuesta(msg) is r
    assert temas.hilo(msg) is None


def test_un_doble_con_atributos_automaticos_no_parece_un_tema():
    """MagicMock contesta a todo: ni es tema ni su respuesta es el inicio de uno."""
    msg = MagicMock()
    assert temas.es_tema(msg) is False and temas.hilo(msg) is None
    assert temas.respuesta(msg) is msg.reply_to_message


def test_hilo():
    assert temas.hilo(NS(is_topic_message=True, message_thread_id=TEMA_ECHO)) == TEMA_ECHO
    assert temas.hilo(NS(is_topic_message=False, message_thread_id=None)) is None
    assert temas.tema_bot_api(NS(is_topic_message=False, message_thread_id=None)) == temas.GENERAL


def test_tema_mtproto_con_las_cabeceras_reales():
    # 451505, leído con la cuenta secundaria: en un tema y sin responder a nada.
    sin_responder = NS(reply_to=NS(forum_topic=True, reply_to_msg_id=TEMA_ECHO, reply_to_top_id=None))
    respondiendo = NS(reply_to=NS(forum_topic=True, reply_to_msg_id=451400, reply_to_top_id=TEMA_ECHO))
    en_general = NS(reply_to=None)
    respuesta_en_general = NS(reply_to=NS(forum_topic=False, reply_to_msg_id=451000, reply_to_top_id=None))
    assert temas.tema_mtproto(sin_responder) == TEMA_ECHO
    assert temas.tema_mtproto(respondiendo) == TEMA_ECHO
    assert temas.tema_mtproto(en_general) == temas.GENERAL
    assert temas.tema_mtproto(respuesta_en_general) == temas.GENERAL


def test_nadie_lee_reply_to_message_a_pelo():
    """Con `ast`, no por texto: un comentario que lo nombre no cuenta. Leído a pelo,
    un /warn sin responder dentro de un tema iría contra quien lo abrió."""
    malos = []
    for f in Path("src").rglob("*.py"):
        if f.name == "temas.py":
            continue
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Attribute) and n.attr == "reply_to_message":
                malos.append(f"{f}:{n.lineno}")
    assert not malos, f"usa temas.respuesta(): {malos}"


# ------------------------------------------------------------------ el @admin

@pytest.fixture
def db(tmp_path):
    return DB(str(tmp_path / "t.db"))


def _tl(mid, autor, tema=None):
    rt = None if tema is None else NS(forum_topic=True, reply_to_msg_id=tema, reply_to_top_id=None)
    return NS(id=mid, sender_id=autor, action=None, reply_to=rt)


def _ctx(db, previos=None, foro=True):
    ctx = MagicMock()
    ctx.bot.id = 8837782565
    ctx.bot.set_message_reaction = AsyncMock()
    ctx.bot.copy_message = AsyncMock()
    enviados = iter(range(451508, 451600))
    ctx.bot.send_message = AsyncMock(side_effect=lambda **kw: NS(message_id=next(enviados)))
    ctx.application.job_queue = None
    reporter = None
    if previos is not None:
        cliente = MagicMock()
        cliente.get_messages = AsyncMock(return_value=previos)
        reporter = NS(get_client=lambda: cliente)
    ctx.bot_data = {"cfg": NS(admin_user_id=ADMIN_DM, admin_notify_chat_id=ADMIN_DM),
                    "db": db, "reporter": reporter}
    return ctx


def _admin(foro=True, edit_date=None, tema=None):
    return NS(from_user=NS(id=1848935109, username="Adolfocc", first_name="Adolfo"),
              chat=NS(id=CHAT, username="AlexaEsp", title="Alexa", is_forum=foro),
              chat_id=CHAT, message_id=451506, reply_to_message=None, text="@admin",
              is_topic_message=tema is not None, message_thread_id=tema, edit_date=edit_date)


def _privados(ctx):
    return [c.kwargs for c in ctx.bot.send_message.await_args_list if c.kwargs["chat_id"] == ADMIN_DM]


# Lo que había antes del @admin, del más nuevo al más viejo (como lo da get_messages).
PREVIOS_REALES = [
    _tl(451505, 1848935109, tema=TEMA_ECHO),  # suyo, en otro tema
    _tl(451503, 9266315643),                  # el spam, en General
    _tl(451501, 8886885856),
]


@pytest.mark.asyncio
async def test_el_caso_real_enlaza_el_spam_y_no_el_mensaje_de_otro_tema(db):
    ctx = _ctx(db, PREVIOS_REALES)
    await admin_report.handle_admin_mention(ctx, db, _admin())
    ctx.bot.copy_message.assert_awaited_once()
    assert ctx.bot.copy_message.await_args.kwargs["message_id"] == 451503
    texto = _privados(ctx)[0]["text"]
    assert "https://t.me/AlexaEsp/451503" in texto and "451505" not in texto
    assert db.find_admin_report_by_reported(CHAT, 451503) is not None


@pytest.mark.asyncio
async def test_en_un_tema_busca_el_anterior_de_ese_tema(db):
    previos = [_tl(451505, 1, tema=None), _tl(451504, 2, tema=TEMA_ECHO)]
    ctx = _ctx(db, previos)
    await admin_report.handle_admin_mention(ctx, db, _admin(tema=TEMA_ECHO))
    assert ctx.bot.copy_message.await_args.kwargs["message_id"] == 451504
    confirmacion = [c.kwargs for c in ctx.bot.send_message.await_args_list if c.kwargs["chat_id"] == CHAT][0]
    assert confirmacion["message_thread_id"] == TEMA_ECHO


@pytest.mark.asyncio
async def test_editar_el_admin_no_repite_el_aviso(db):
    ctx = _ctx(db, PREVIOS_REALES)
    await admin_report.handle_admin_mention(ctx, db, _admin())
    antes = ctx.bot.send_message.await_count
    await admin_report.handle_admin_mention(ctx, db, _admin(edit_date=object()))
    assert ctx.bot.send_message.await_count == antes, "la edición volvió a avisar"


@pytest.mark.asyncio
async def test_sin_cuenta_secundaria_en_un_foro_no_adivina_pero_avisa(db):
    ctx = _ctx(db, previos=None)
    await admin_report.handle_admin_mention(ctx, db, _admin(foro=True))
    ctx.bot.copy_message.assert_not_awaited()
    privados = _privados(ctx)
    assert len(privados) == 1
    assert "https://t.me/AlexaEsp/451506" in privados[0]["text"]  # al propio @admin


@pytest.mark.asyncio
async def test_sin_cuenta_secundaria_en_un_grupo_normal_sigue_el_id_anterior(db):
    ctx = _ctx(db, previos=None)
    await admin_report.handle_admin_mention(ctx, db, _admin(foro=False))
    assert ctx.bot.copy_message.await_args.kwargs["message_id"] == 451505


@pytest.mark.asyncio
async def test_si_la_copia_falla_el_aviso_sale_igual(db):
    ctx = _ctx(db, PREVIOS_REALES)
    ctx.bot.copy_message = AsyncMock(side_effect=BadRequest("Message can't be copied"))
    await admin_report.handle_admin_mention(ctx, db, _admin())
    assert len(_privados(ctx)) == 1


@pytest.mark.asyncio
async def test_si_la_cuenta_secundaria_falla_el_aviso_sale_igual(db):
    ctx = _ctx(db, PREVIOS_REALES)
    ctx.bot_data["reporter"].get_client().get_messages = AsyncMock(side_effect=RuntimeError("red"))
    await admin_report.handle_admin_mention(ctx, db, _admin(foro=True))
    assert len(_privados(ctx)) == 1


@pytest.mark.asyncio
async def test_el_agradecimiento_va_al_tema_del_admin(db, monkeypatch):
    db.add_admin_report(chat_id=CHAT, reporter_msg_id=451506, reporter_user_id=1, reporter_username=None,
                        reported_msg_id=451503, reported_user_id=None, bot_confirm_msg_id=None,
                        thread_id=TEMA_ECHO)
    bot = MagicMock()
    bot.delete_message = AsyncMock()
    bot.send_message = AsyncMock(return_value=NS(message_id=9))
    monkeypatch.setattr(admin_report, "_delayed_delete", AsyncMock())
    await admin_report.on_reported_message_deleted(bot, db, CHAT, 451503)
    assert bot.send_message.await_args.kwargs["message_thread_id"] == TEMA_ECHO
