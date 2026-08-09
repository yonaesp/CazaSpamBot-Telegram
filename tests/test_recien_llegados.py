"""La ventana ciega entre entrar y escribir.

El bot miraba a cada usuario DOS veces: al entrar y al escribir su primer mensaje.
Entre las dos pueden pasar horas, y ahí se colaban dos cosas medidas en el grupo de
domótica:

1. **lols.bot ficha tarde.** Se alimenta de denuncias, así que un spammer recién
   creado está limpio cuando entra. Medido: 1 h 35 min, 12 h 14 min y 27 h entre la
   entrada (limpio) y el primer mensaje (ya fichado). No es que el bot «esperase a
   que escribieran»: preguntó al entrar y le dijeron que no había nada.
2. **El nombre se cambia después de verificarse.** El 8953604344 pulsó el botón de
   verificación en 3 segundos y doce horas más tarde escribía como `唔活诗我`. Con
   ese nombre no habría entrado: `_is_obvious_spam_profile` lo banea. Se lo puso ya
   dentro, y el perfil no se volvía a mirar nunca.
"""
import time
from types import SimpleNamespace

import pytest

from src import recien_llegados as rl
from src.db import DB
from src.detectors import Hit
from src.verification import _is_obvious_spam_profile


def _db(tmp_path) -> DB:
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(-100, "Domótica", "supergroup", True, True, True)
    return db


# ------------------------------------------------- a quién se vigila y a quién no

def test_solo_los_que_entraron_hace_poco_y_no_han_escrito(tmp_path):
    db = _db(tmp_path)
    ahora = time.time()
    db.record_join(-100, 1, "recien", join_ts=ahora - 600)          # candidato
    db.record_join(-100, 2, "hablador", join_ts=ahora - 600)
    db.record_message(-100, 2, "hablador")                          # ya escribió
    db.record_join(-100, 3, "antiguo", join_ts=ahora - 40 * 3600)   # fuera de ventana

    ids = {f["user_id"] for f in db.recien_llegados_callados(ahora - rl.VENTANA_S)}
    assert ids == {1}


def test_la_lista_blanca_queda_fuera(tmp_path):
    """A quien el admin ha marcado como de fiar no se le vuelve a interrogar."""
    db = _db(tmp_path)
    ahora = time.time()
    db.record_join(-100, 7, "amigo", join_ts=ahora - 600)
    db.whitelist(-100, 7)
    assert db.recien_llegados_callados(ahora - rl.VENTANA_S) == []


def test_a_la_misma_persona_no_se_le_pregunta_a_cada_vuelta():
    """El trabajo corre cada 15 min y las listas son APIs de terceros: sin esta
    espera se les consultaría cuatro veces por hora y por persona."""
    ctx = SimpleNamespace(bot_data={})
    assert rl._toca_mirar(ctx, -100, 1) is True
    assert rl._toca_mirar(ctx, -100, 1) is False, "se estaría preguntando de más"
    assert rl._toca_mirar(ctx, -100, 2) is True, "otra persona sí se mira"


def test_el_recuerdo_de_quien_ya_se_miro_no_crece_sin_fin():
    ctx = SimpleNamespace(bot_data={})
    rl._toca_mirar(ctx, -100, 1)
    ctx.bot_data[rl._CLAVE_CACHE][(-100, 1)] = time.time() - rl.VENTANA_S - 10
    rl._toca_mirar(ctx, -100, 2)
    assert (-100, 1) not in ctx.bot_data[rl._CLAVE_CACHE]


# ------------------------------------------------------------- lo que se hace

class _Bot:
    def __init__(self):
        self.baneados = []

    async def ban_chat_member(self, chat_id, user_id, **kw):
        self.baneados.append(user_id)
        return True

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(user=SimpleNamespace(
            id=user_id, is_bot=False, first_name="Juan", last_name=None, username=None))

    async def send_message(self, *a, **kw):
        return SimpleNamespace(message_id=1)

    async def delete_message(self, *a, **kw):
        return True

    async def get_chat(self, chat_id):
        return SimpleNamespace(id=chat_id, title="Domótica")


def _ctx(db, bot, cfg):
    return SimpleNamespace(
        bot=bot,
        bot_data={"db": db, "cfg": cfg, "http": object(), "reporter": None},
        application=SimpleNamespace(job_queue=None),
    )


def _cfg(**extra):
    base = dict(
        lols_enabled=True, cas_enabled=False, cas_autoban_min=2, cas_cache_ttl_seconds=3600,
        ban_score=100, kick_score=70, mute_score=40, first_msg_attack_action="ban",
        shadow=False, mode="active", admin_user_id=1, admin_notify_chat_id=None,
        public_quip_enabled=False, moderated_chat_ids=[], allowed_scripts=["latin"],
    )
    base.update(extra)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_si_lols_lo_ficha_despues_se_banea_sin_esperar_a_que_escriba(tmp_path, monkeypatch):
    """El caso de @Juan: entró limpio a las 07:14 y a las 08:49 ya estaba fichado."""
    db = _db(tmp_path)
    db.record_join(-100, 555, "juan", join_ts=time.time() - 5400)
    bot, cfg = _Bot(), _cfg()
    ctx = _ctx(db, bot, cfg)

    async def falso_lols(user_id, session):
        return Hit(rule="lols_match", score=100, reason="fichado", payload={})
    monkeypatch.setattr(rl.lols_det, "check", falso_lols)

    aplicado = {}

    async def falso_apply(context, db_, cfg_, **kw):
        aplicado.update(kw)
    monkeypatch.setattr("src.handlers._apply_action", falso_apply)
    monkeypatch.setattr("src.handlers._trust_score_cached", lambda *a, **k: 0)

    await rl.revisar_job(ctx)
    assert aplicado.get("user_id") == 555
    assert aplicado["decision"].action == "ban"


@pytest.mark.asyncio
async def test_al_veterano_fichado_no_se_le_autobanea(tmp_path, monkeypatch):
    """Mismo criterio que en el join: un veterano en una lista externa huele a
    falso positivo de la lista. Se anota y decide un humano."""
    db = _db(tmp_path)
    db.record_join(-100, 556, "veterano", join_ts=time.time() - 3600)
    bot, cfg = _Bot(), _cfg()
    ctx = _ctx(db, bot, cfg)

    async def falso_lols(user_id, session):
        return Hit(rule="lols_match", score=100, reason="fichado", payload={})
    monkeypatch.setattr(rl.lols_det, "check", falso_lols)
    monkeypatch.setattr("src.handlers._trust_score_cached", lambda *a, **k: 95)

    llamado = []
    monkeypatch.setattr("src.handlers._apply_action",
                        lambda *a, **k: llamado.append(1))

    await rl.revisar_job(ctx)
    assert not llamado, "un veterano no puede caer por una lista externa sin revisión"
    filas = [dict(r) for r in db.recent_actions(limit=5)]
    assert any(f["rule"] == "lols_match_trusted_review" for f in filas)


@pytest.mark.asyncio
async def test_el_nombre_puesto_despues_de_verificarse_tambien_cuenta(tmp_path, monkeypatch):
    """El caso 8953604344: entró con un nombre que pasó el filtro, se verificó en
    3 segundos y luego se puso `唔活诗我`, que al entrar le habría costado el ban."""
    db = _db(tmp_path)
    db.record_join(-100, 557, None, join_ts=time.time() - 7200)
    cfg = _cfg(lols_enabled=False, cas_enabled=False)

    class BotConNombreNuevo(_Bot):
        async def get_chat_member(self, chat_id, user_id):
            return SimpleNamespace(chat=SimpleNamespace(id=chat_id, title="Domótica"),
                                   user=SimpleNamespace(
                                       id=user_id, is_bot=False, first_name="唔活诗我",
                                       last_name=None, username="zBuepQqZEcvifAeaGK"))

    ctx = _ctx(db, BotConNombreNuevo(), cfg)
    aplicado = {}

    async def falso_apply(context, db_, cfg_, **kw):
        aplicado.update(kw)
    monkeypatch.setattr("src.handlers._apply_action", falso_apply)

    await rl.revisar_job(ctx)
    assert aplicado.get("user_id") == 557
    assert aplicado["decision"].rule == "obvious_spam_profile"


def test_ese_nombre_habria_impedido_la_entrada():
    """La premisa del test anterior: con ese nombre el join lo banea. Si esto
    cambiara, vigilar el perfil después de entrar dejaría de tener sentido."""
    assert _is_obvious_spam_profile(None, "zBuepQqZEcvifAeaGK", "唔活诗我")[0]
    assert not _is_obvious_spam_profile(None, None, "Juan")[0]


@pytest.mark.asyncio
async def test_un_fallo_consultando_a_uno_no_deja_sin_mirar_al_resto(tmp_path, monkeypatch):
    db = _db(tmp_path)
    ahora = time.time()
    for uid in (601, 602, 603):
        db.record_join(-100, uid, None, join_ts=ahora - 600)
    ctx = _ctx(db, _Bot(), _cfg())
    vistos = []

    async def revienta(context, db_, cfg_, session, fila):
        vistos.append(fila["user_id"])
        raise RuntimeError("la API no responde")
    monkeypatch.setattr(rl, "_revisar_uno", revienta)

    await rl.revisar_job(ctx)
    assert len(vistos) == 3, "un fallo cortaba el repaso de los demás"


# ---------------------------------------------------------------------------
# El canal del perfil, que la Bot API no enseña
#
# Tercera vía por la que se colaban, medida el 2026-08-08 en Windows 11:
# «Vickycat46», nombre latino, foto de perfil normal y un canal enlazado en el
# perfil titulado `恒泰招聘车队高速结算`, reclutando mulas de blanqueo.
#
# El repaso de recién llegados no lo veía por una razón de diseño: solo leía el
# perfil por Telethon si el NOMBRE ya era sospechoso de por sí, y ese nombre es
# perfectamente normal. El canal solo se ve por MTProto, así que había que
# aceptar leer algunos perfiles limpios (con presupuesto) para llegar a él.
# ---------------------------------------------------------------------------

class _Sig:
    """Lo que devuelve `user_signals.fetch`, en lo que aquí importa."""
    def __init__(self, titulo=None):
        self.personal_channel_title = titulo
        self.personal_channel_id = 4412923989
        self.personal_channel_entity = object()
        self.photo_count = 1          # tiene foto: por eso se libraba antes
        self.bio = None


def _ctx_con_telethon(db, bot, cfg, sig):
    ctx = _ctx(db, bot, cfg)
    ctx.bot_data["reporter"] = SimpleNamespace(get_client=lambda: object())
    return ctx


@pytest.mark.asyncio
async def test_el_canal_de_spam_se_caza_sin_esperar_a_que_escriba(tmp_path, monkeypatch):
    db = _db(tmp_path)
    db.record_join(-100, 8878951888, None, join_ts=time.time() - 7200)
    ctx = _ctx_con_telethon(db, _Bot(), _cfg(lols_enabled=False), _Sig())

    async def falso_fetch(client, user_id, **kw):
        return _Sig("恒泰招聘车队高速结算")
    monkeypatch.setattr("src.user_signals.fetch", falso_fetch)

    aplicado = {}

    async def falso_apply(context, db_, cfg_, **kw):
        aplicado.update(kw)
    monkeypatch.setattr("src.handlers._apply_action", falso_apply)

    await rl.revisar_job(ctx)
    assert aplicado.get("user_id") == 8878951888
    assert aplicado["decision"].rule == "personal_channel_spam"
    assert aplicado["decision"].payload["via"] == "recien_llegados"


@pytest.mark.asyncio
async def test_un_perfil_limpio_con_canal_normal_no_se_toca(tmp_path, monkeypatch):
    """Tener canal personal es legítimo. Lo que delata es la discordancia."""
    db = _db(tmp_path)
    db.record_join(-100, 900, None, join_ts=time.time() - 7200)
    ctx = _ctx_con_telethon(db, _Bot(), _cfg(lols_enabled=False), _Sig())

    async def falso_fetch(client, user_id, **kw):
        return _Sig("Mis fotos de montaña")
    monkeypatch.setattr("src.user_signals.fetch", falso_fetch)

    llamado = []
    monkeypatch.setattr("src.handlers._apply_action",
                        lambda *a, **k: llamado.append(1))

    await rl.revisar_job(ctx)
    assert not llamado


@pytest.mark.asyncio
async def test_sin_telethon_el_repaso_sigue_funcionando(tmp_path, monkeypatch):
    """Quien instale el bot sin cuenta secundaria pierde esta vía, no el bot."""
    db = _db(tmp_path)
    db.record_join(-100, 901, None, join_ts=time.time() - 7200)
    ctx = _ctx(db, _Bot(), _cfg(lols_enabled=False))   # reporter=None
    llamado = []
    monkeypatch.setattr("src.handlers._apply_action",
                        lambda *a, **k: llamado.append(1))
    await rl.revisar_job(ctx)
    assert not llamado


# ------------------------------------------------------- el freno de las lecturas

def test_se_leen_pocos_perfiles_por_vuelta():
    """Leer un perfil son varias llamadas MTProto con la cuenta secundaria. Sin
    presupuesto serían 25 cada cuarto de hora, que es como se gana un FloodWait
    (regla 9: proteger la reputación de esa cuenta)."""
    ctx = SimpleNamespace(bot_data={rl._CLAVE_PRESUPUESTO: rl.MAX_PERFILES_POR_CICLO})
    leidos = sum(1 for uid in range(100) if rl._toca_leer_perfil(ctx, -100, uid))
    assert leidos == rl.MAX_PERFILES_POR_CICLO


def test_el_presupuesto_se_renueva_en_cada_vuelta():
    ctx = SimpleNamespace(bot_data={rl._CLAVE_PRESUPUESTO: 1})
    assert rl._toca_leer_perfil(ctx, -100, 1) is True
    assert rl._toca_leer_perfil(ctx, -100, 2) is False
    ctx.bot_data[rl._CLAVE_PRESUPUESTO] = rl.MAX_PERFILES_POR_CICLO
    assert rl._toca_leer_perfil(ctx, -100, 3) is True


def test_al_mismo_perfil_no_se_vuelve_enseguida():
    """Un canal personal no aparece y desaparece: con mirarlo un par de veces en
    la ventana de un día sobra."""
    ctx = SimpleNamespace(bot_data={rl._CLAVE_PRESUPUESTO: 50})
    assert rl._toca_leer_perfil(ctx, -100, 1) is True
    assert rl._toca_leer_perfil(ctx, -100, 1) is False
    assert rl._toca_leer_perfil(ctx, -100, 2) is True


def test_el_recuerdo_de_perfiles_leidos_no_crece_sin_fin():
    ctx = SimpleNamespace(bot_data={rl._CLAVE_PRESUPUESTO: 50})
    rl._toca_leer_perfil(ctx, -100, 1)
    ctx.bot_data[rl._CLAVE_PERFILES][(-100, 1)] = time.time() - rl.VENTANA_S - 10
    rl._toca_leer_perfil(ctx, -100, 2)
    assert (-100, 1) not in ctx.bot_data[rl._CLAVE_PERFILES]


def test_el_repaso_usa_el_mismo_criterio_que_el_join():
    """Sin esto habría dos varas de medir: lo que aquí se banea tiene que ser
    exactamente lo que se habría baneado al entrar."""
    from pathlib import Path
    fuente = Path("src/recien_llegados.py").read_text()
    assert "_mirar_canal_personal" in fuente, "debe reutilizar el helper del handler"
    assert "personal_channel_det.check" not in fuente, "no puede tener su propia lógica"
