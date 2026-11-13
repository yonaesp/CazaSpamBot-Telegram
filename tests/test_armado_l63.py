"""El armado: entrar con el perfil vacío y ponérselo minutos antes de escribir (L63).

Caso real (13-nov-2026, Windows 10): «Cortney» entró a las 04:38 sin foto, sin @ y
sin bio, y lols.bot no la tenía. A las 07:56 lols la fichó; a las 08:00:46 escribió
con la foto, el @ y la bio «https://t.me/+… 新人有码进群 私信老板日入8000+» puestos.
El repaso había pasado a las 07:49 y volvía a las 08:04: la baneó el primer mensaje.
"""
from __future__ import annotations

import ast
import logging
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from telegram.error import BadRequest, RetryAfter

from src import recien_llegados as rl
from src.db import DB
from src.detectors import Hit

CHAT = -1001008178265
CORTNEY = 9159287262
BIO = "https://t.me/+yL2n0c7nmmcyOGU1 新人有码进群 私信老板日入8000+"
SRC = Path(__file__).resolve().parent.parent / "src"


class _Bot:
    """La Bot API en lo que aquí importa: `getChat` da el perfil que haya en ese momento."""

    def __init__(self, perfiles: dict | None = None):
        self.perfiles = perfiles or {}
        self.consultados: list[int] = []
        self.falla: dict[int, Exception] = {}

    async def get_chat(self, chat_id):
        self.consultados.append(chat_id)
        if chat_id in self.falla:
            raise self.falla[chat_id]
        return NS(id=chat_id, **self.perfiles.get(chat_id, {"first_name": "Cortney"}))

    async def get_chat_member(self, chat_id, user_id):
        p = self.perfiles.get(user_id, {})
        return NS(user=NS(id=user_id, is_bot=False, first_name=p.get("first_name", "Cortney"),
                          last_name=None, username=p.get("username")))


class _Sig:
    """Lo que devuelve `user_signals.fetch` (la lectura completa, por Telethon)."""

    def __init__(self, bio=None, fotos=0, dias=20, canal=None):
        self.bio, self.photo_count, self.account_age_days = bio, fotos, dias
        self.personal_channel_title, self.personal_channel_id = canal, None
        self.personal_channel_entity = None
        self.tiene_posts, self.entidad, self.is_premium = False, None, False


def _cfg(**extra):
    base = dict(
        lols_enabled=False, cas_enabled=False, cas_autoban_min=2, cas_cache_ttl_seconds=3600,
        ban_score=100, kick_score=70, mute_score=40, first_msg_attack_action="ban",
        shadow=False, mode="active", admin_user_id=1, admin_notify_chat_id=None,
        public_quip_enabled=False, moderated_chat_ids=[], allowed_scripts=["latin"],
    )
    base.update(extra)
    return NS(**base)


@pytest.fixture
def e(tmp_path, monkeypatch):
    """Una cuenta dentro desde hace 3 h, sin escribir, con el perfil vacío."""
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(CHAT, "Windows 10", "supergroup", True, True, True)
    db.record_join(CHAT, CORTNEY, None, join_ts=time.time() - 3 * 3600)
    bot = _Bot()
    ctx = NS(bot=bot, application=NS(job_queue=None),
             bot_data={"db": db, "cfg": _cfg(), "http": object(),
                       "reporter": NS(get_client=lambda: object())})
    env = NS(db=db, bot=bot, ctx=ctx, sig=_Sig(), lecturas=[], aplicado=[])

    async def fetch(client, user_id, **kw):
        env.lecturas.append(user_id)
        return env.sig

    async def aplicar(context, db_, cfg_, **kw):
        env.aplicado.append(kw)

    monkeypatch.setattr("src.user_signals.fetch", fetch)
    monkeypatch.setattr("src.handlers._apply_action", aplicar)
    monkeypatch.setattr("src.handlers._trust_score_cached", lambda *a, **k: 0)
    return env


def _armar(e, **perfil):
    e.bot.perfiles[CORTNEY] = {"first_name": "Cortney", **perfil}


# --------------------------------------------------------------- la huella

def test_la_huella_recoge_lo_que_se_arma():
    vacia = rl._huella(NS(first_name="Cortney"))
    assert vacia == ("Cortney", "", "", "", "")
    armada = rl._huella(NS(first_name="Cortney", last_name="Cowen", username="zaHCQOeGQtiVtgoXVls",
                           bio=BIO, photo=NS(big_file_unique_id="AQADx"), personal_chat=NS(id=-100123)))
    assert armada == ("Cortney Cowen", "zaHCQOeGQtiVtgoXVls", BIO, "AQADx", "-100123")
    assert len(armada) == len(rl._CAMPOS_HUELLA)


# ------------------------------------------------------ el caso de Cortney

@pytest.mark.asyncio
async def test_quien_se_arma_cae_sin_esperar_a_que_escriba(e, caplog):
    await rl.vigilar_armado_job(e.ctx)                 # primera pasada: solo toma nota
    assert e.lecturas == [] and e.aplicado == []

    _armar(e, username="zaHCQOeGQtiVtgoXVls", bio=BIO, photo=NS(big_file_unique_id="AQADx"))
    e.sig = _Sig(bio=BIO, fotos=1)
    with caplog.at_level(logging.INFO, logger="src.recien_llegados"):
        await rl.vigilar_armado_job(e.ctx)

    assert e.lecturas == [CORTNEY], "el cambio dispara UNA lectura completa"
    (kw,) = e.aplicado
    assert kw["user_id"] == CORTNEY and kw["decision"].action == "ban"
    assert kw["decision"].payload["via"] == "recien_llegados"
    assert "armado: user=9159287262 ha cambiado usuario+bio+foto" in caplog.text


@pytest.mark.asyncio
async def test_sin_cambios_no_se_gasta_ni_una_lectura(e):
    for _ in range(5):
        await rl.vigilar_armado_job(e.ctx)
    assert e.bot.consultados == [CORTNEY] * 5, "la Bot API sí se consulta en cada pasada"
    assert e.lecturas == [] and e.aplicado == []


@pytest.mark.asyncio
async def test_la_primera_vez_que_se_ve_a_alguien_no_dispara(e):
    """Tras un reinicio no hay huella anterior: todos «nuevos», ninguno «cambiado»."""
    _armar(e, bio="Fan de Windows desde el 95", photo=NS(big_file_unique_id="A"))
    await rl.vigilar_armado_job(e.ctx)
    assert e.lecturas == []


@pytest.mark.asyncio
async def test_el_segundo_cambio_de_una_rafaga_no_se_pierde(e):
    """Primero la foto y, un minuto después, la bio: la espera de 120 s entre
    disparos de `revisar_ahora` se habría comido el segundo, que es el que banea."""
    await rl.vigilar_armado_job(e.ctx)
    _armar(e, photo=NS(big_file_unique_id="AQADx"))
    e.sig = _Sig(fotos=1)
    await rl.vigilar_armado_job(e.ctx)
    assert e.lecturas == [CORTNEY] and e.aplicado == []

    _armar(e, photo=NS(big_file_unique_id="AQADx"), bio=BIO)
    e.sig = _Sig(bio=BIO, fotos=1)
    await rl.vigilar_armado_job(e.ctx)
    assert e.lecturas == [CORTNEY, CORTNEY]
    assert len(e.aplicado) == 1 and e.aplicado[0]["decision"].action == "ban"


@pytest.mark.asyncio
async def test_un_perfil_normal_que_cambia_no_se_toca(e):
    """El cambio no decide nada: una persona que se pone foto y una bio corriente
    solo cuesta una lectura."""
    await rl.vigilar_armado_job(e.ctx)
    _armar(e, username="pepe_garcia", bio="Informático. Mi blog: https://pepe.example",
           photo=NS(big_file_unique_id="B"))
    e.sig = _Sig(bio="Informático. Mi blog: https://pepe.example", fotos=1)
    await rl.vigilar_armado_job(e.ctx)
    assert e.lecturas == [CORTNEY] and e.aplicado == []


@pytest.mark.asyncio
async def test_al_armarse_se_miran_tambien_las_listas(e, monkeypatch):
    """lols fichó a Cortney 4 minutos antes de que escribiera aquí."""
    e.ctx.bot_data["cfg"] = _cfg(lols_enabled=True)

    async def lols(user_id, session):
        return Hit(rule="lols_match", score=100, reason="fichado", payload={"banned": True})
    monkeypatch.setattr(rl.lols_det, "check", lols)

    await rl.vigilar_armado_job(e.ctx)
    assert e.aplicado == [], "sin cambio no se consulta a nadie"
    _armar(e, photo=NS(big_file_unique_id="AQADx"))        # perfil aún sin nada que banear
    e.sig = _Sig(fotos=1)
    await rl.vigilar_armado_job(e.ctx)
    (kw,) = e.aplicado
    assert kw["decision"].rule == "lols_match" and kw["decision"].action == "ban"


# ------------------------------------------------------------------ frenos

@pytest.mark.asyncio
async def test_cambiarse_el_perfil_en_bucle_no_da_una_lectura_por_minuto(e):
    await rl.vigilar_armado_job(e.ctx)
    for i in range(rl.MAX_DISPAROS_ARMADO + 5):
        _armar(e, bio=f"bio número {i}")
        e.sig = _Sig(bio=f"bio número {i}")
        await rl.vigilar_armado_job(e.ctx)
    assert len(e.lecturas) == rl.MAX_DISPAROS_ARMADO


@pytest.mark.asyncio
async def test_si_telegram_pide_frenar_la_vigilancia_se_aparta(e, caplog):
    e.db.record_join(CHAT, 2, None, join_ts=time.time() - 60)
    e.db.record_join(CHAT, 3, None, join_ts=time.time() - 30)
    e.bot.falla[2] = RetryAfter(30)
    with caplog.at_level(logging.WARNING, logger="src.recien_llegados"):
        await rl.vigilar_armado_job(e.ctx)
    assert e.bot.consultados == [3, 2], "al 429 se deja la pasada: ni una llamada más"
    assert "Telegram pide frenar" in caplog.text

    e.bot.falla.clear()
    await rl.vigilar_armado_job(e.ctx)
    assert e.bot.consultados == [3, 2], "en pausa no se pregunta nada"
    e.ctx.bot_data[rl._CLAVE_ARMADO]["pausa"] = time.time() - 1
    await rl.vigilar_armado_job(e.ctx)
    assert len(e.bot.consultados) == 5


@pytest.mark.asyncio
async def test_un_perfil_que_no_se_deja_leer_no_frena_al_resto(e):
    e.db.record_join(CHAT, 2, None, join_ts=time.time() - 60)
    e.bot.falla[2] = BadRequest("Chat not found")
    await rl.vigilar_armado_job(e.ctx)
    assert e.bot.consultados == [2, CORTNEY]
    assert e.ctx.bot_data[rl._CLAVE_ARMADO]["fallos"] == 1


@pytest.mark.asyncio
async def test_a_los_baneados_y_a_quien_ya_escribio_no_se_les_pregunta(e):
    e.db.record_join(CHAT, 2, None, join_ts=time.time() - 60)
    e.db.record_message(CHAT, 2, None)                       # ya escribió: lo mira su primer mensaje
    e.db.record_join(CHAT, 3, None, join_ts=time.time() - 60)
    e.db.add_ban(3, "x", "lols_match", CHAT)
    await rl.vigilar_armado_job(e.ctx)
    assert e.bot.consultados == [CORTNEY]


@pytest.mark.asyncio
async def test_quien_esta_en_dos_grupos_se_consulta_una_vez(e):
    e.db.upsert_bot_chat(-1001190184646, "Domótica", "supergroup", True, True, True)
    e.db.record_join(-1001190184646, CORTNEY, None, join_ts=time.time() - 3600)
    await rl.vigilar_armado_job(e.ctx)
    assert e.bot.consultados == [CORTNEY]


@pytest.mark.asyncio
async def test_el_minuto_mira_el_primer_dia_y_el_repaso_la_semana(e):
    e.db.record_join(CHAT, 2, None, join_ts=time.time() - 3 * 86400)     # tercer día
    await rl.vigilar_armado_job(e.ctx)
    assert e.bot.consultados == [CORTNEY]
    await rl._vigilar_armado(e.ctx, rl.VENTANA_S, rl.MAX_NOMBRES_POR_CICLO)
    assert sorted(e.bot.consultados[1:]) == sorted([CORTNEY, 2])


@pytest.mark.asyncio
async def test_una_avalancha_no_pasa_del_tope_por_pasada(e):
    for uid in range(1000, 1000 + rl.MAX_ARMADO_POR_PASADA + 40):
        e.db.record_join(CHAT, uid, None, join_ts=time.time() - 600)
    await rl.vigilar_armado_job(e.ctx)
    assert len(e.bot.consultados) == rl.MAX_ARMADO_POR_PASADA


@pytest.mark.asyncio
async def test_el_latido_sale_una_vez_a_la_hora(e, caplog):
    with caplog.at_level(logging.INFO, logger="src.recien_llegados"):
        await rl.vigilar_armado_job(e.ctx)
        assert "armado:" not in caplog.text, "una línea por minuto llenaría el log"
        e.ctx.bot_data[rl._CLAVE_ARMADO]["latido"] = time.time() - 3601
        await rl.vigilar_armado_job(e.ctx)
    assert "armado: 1 perfiles vigilados, 2 consultas, 0 sin respuesta y 0 cambios" in caplog.text
    assert e.ctx.bot_data[rl._CLAVE_ARMADO]["consultas"] == 0


@pytest.mark.asyncio
async def test_si_nadie_responde_durante_una_hora_se_avisa(e, caplog):
    """No poder mirar no es «todo bien»: una hora entera sin una sola respuesta se dice."""
    e.bot.falla[CORTNEY] = BadRequest("Chat not found")
    await rl.vigilar_armado_job(e.ctx)
    e.ctx.bot_data[rl._CLAVE_ARMADO]["latido"] = time.time() - 3601
    with caplog.at_level(logging.WARNING, logger="src.recien_llegados"):
        await rl.vigilar_armado_job(e.ctx)
    assert "no se está vigilando a nadie" in caplog.text


@pytest.mark.asyncio
async def test_las_huellas_de_quien_ya_no_se_vigila_se_olvidan(e):
    await rl.vigilar_armado_job(e.ctx)
    huellas = e.ctx.bot_data[rl._CLAVE_HUELLAS]
    huellas[777] = (("x", "", "", "", ""), time.time() - rl.VENTANA_S - 10)
    await rl.vigilar_armado_job(e.ctx)
    assert set(huellas) == {CORTNEY}


@pytest.mark.asyncio
async def test_un_fallo_en_la_pasada_no_sale_del_trabajo(e, monkeypatch, caplog):
    monkeypatch.setattr(e.db, "recien_llegados_callados", lambda *a, **k: 1 / 0)
    with caplog.at_level(logging.WARNING, logger="src.recien_llegados"):
        await rl.vigilar_armado_job(e.ctx)
    assert "armado: fallo en la pasada" in caplog.text


# ---------------------------- el repaso aplica el criterio del join entero

@pytest.mark.asyncio
async def test_una_bio_en_otro_alfabeto_puesta_despues_cae_en_el_repaso(e):
    """Sin enlace `bio_spam` no salta, y el criterio de alfabeto solo se miraba
    si el NOMBRE ya disparaba: con el nombre limpio no se llegaba nunca."""
    e.sig = _Sig(bio="新人有码进群 私信老板日入8000+", fotos=1)
    await rl.revisar_job(e.ctx)
    (kw,) = e.aplicado
    assert kw["decision"].rule == "obvious_spam_profile" and kw["decision"].action == "ban"
    assert kw["decision"].payload["via"] == "recien_llegados"


@pytest.mark.asyncio
@pytest.mark.parametrize("bio", ["Люблю Windows y la domótica", "Me gusta Windows 11 ツ", None])
async def test_con_el_nombre_limpio_una_bio_normal_no_cambia_nada(e, bio):
    e.sig = _Sig(bio=bio, fotos=1, dias=900)
    await rl.revisar_job(e.ctx)
    assert e.aplicado == []


@pytest.mark.asyncio
async def test_el_mudo_por_nombre_han_sigue_siendo_solo_por_el_nombre(e, monkeypatch):
    """Con el nombre limpio no se pregunta `han_requiere_decision`: a quien el
    admin ya dejó pasar no se le silencia otra vez en cada lectura del perfil."""
    from src import verification
    preguntado = []
    monkeypatch.setattr(verification, "han_requiere_decision",
                        lambda *a, **k: preguntado.append(1) or True)
    e.sig = _Sig(fotos=3, dias=900)
    await rl.revisar_job(e.ctx)
    assert preguntado == [] and e.aplicado == []


# ------------------------------------------------------------ estructura

def _fn(nombre: str, fichero: str = "recien_llegados.py"):
    arbol = ast.parse((SRC / fichero).read_text(encoding="utf-8"))
    return next(n for n in ast.walk(arbol)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre)


def _nombres(fn) -> set[str]:
    return {n.attr if isinstance(n, ast.Attribute) else n.id
            for n in ast.walk(fn) if isinstance(n, (ast.Attribute, ast.Name))}


def test_la_vigilancia_no_decide_ni_toca_la_cuenta_secundaria():
    """Ni criterios propios ni Telethon: solo Bot API y «mira a este ya»."""
    usados = _nombres(_fn("_vigilar_armado"))
    assert "revisar_ahora" in usados and "get_chat" in usados
    assert not usados & {"_apply_action", "Decision", "ban_chat_member", "get_client",
                         "user_signals", "bio_spam", "_is_obvious_spam_profile"}


def test_el_trabajo_del_minuto_esta_programado():
    arbol = ast.parse((SRC / "main.py").read_text(encoding="utf-8"))
    del_armado = [n for n in ast.walk(arbol)
                  if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "run_repeating"
                  and "vigilar_armado_job" in ast.dump(n.args[0])]
    assert len(del_armado) == 1
    intervalo = next(k.value for k in del_armado[0].keywords if k.arg == "interval")
    assert "ARMADO_CADA_S" in ast.dump(intervalo)
    assert 30 <= rl.ARMADO_CADA_S <= 120, "los casos medidos dejaron 3,5 y 4,6 min"


def test_el_join_dice_cuanto_perfil_habia():
    """Sin esto, «entró vacía y se armó dentro» era una deducción y no un dato."""
    fuente = (SRC / "handlers.py").read_text(encoding="utf-8")
    assert "señales=%s canal=%s bio=%s fotos=%s usuario=%s" in fuente
