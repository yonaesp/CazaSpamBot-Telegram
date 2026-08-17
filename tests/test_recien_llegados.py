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
    # Fuera de ventana: 8 días. Las 40 h de antes quedaron DENTRO cuando la
    # ventana pasó de 24 h a 7 días (el 7688429577 esperó a las 29,6 h).
    db.record_join(-100, 3, "antiguo", join_ts=ahora - 8 * 86400)

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

    async def revienta(context, db_, cfg_, session, fila, espera):
        vistos.append(fila["user_id"])
        raise RuntimeError("la API no responde")
    monkeypatch.setattr(rl, "_revisar_listas", revienta)

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


# ---------------------------------------------------------------------------
# El nombre es gratis; las listas externas no
#
# Los dos frenos eran el mismo (una hora), y no tienen por qué serlo:
#
#   - `get_chat_member` es **Bot API**: gratis, sin límite práctico y sin tocar
#     la cuenta secundaria de Telethon. Y el nombre es justo lo que cambia,
#     porque el truco consiste en entrar con uno que pasa los filtros y ponerse
#     el de verdad poco antes de hablar.
#   - CAS y lols.bot son **APIs de terceros**, y ahí sí conviene espaciar.
#
# Ponerle a lo gratis el freno de lo caro era regalarle al spammer una hora a
# cambio de nada. Caso que lo destapó: «李大哥» entró a las 00:39 con el perfil
# limpio y escribió a las 15:29 con nombre 100 % Han.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_el_nombre_se_mira_en_cada_vuelta(tmp_path, monkeypatch):
    """Sin espera: dos vueltas seguidas tienen que leer el nombre las dos veces."""
    db = _db(tmp_path)
    db.record_join(-100, 700, None, join_ts=time.time() - 600)
    leidos = []

    class BotQueCuenta(_Bot):
        async def get_chat_member(self, chat_id, user_id):
            leidos.append(user_id)
            return SimpleNamespace(user=SimpleNamespace(
                id=user_id, is_bot=False, first_name="Ana", last_name=None, username=None))

    ctx = _ctx(db, BotQueCuenta(), _cfg(lols_enabled=False, cas_enabled=False))
    await rl.revisar_job(ctx)
    await rl.revisar_job(ctx)
    assert leidos == [700, 700], "el nombre solo se miró una vez: vuelve a haber espera"


@pytest.mark.asyncio
async def test_las_listas_externas_si_esperan(tmp_path, monkeypatch):
    """La contrapartida: lo caro se sigue espaciando."""
    db = _db(tmp_path)
    db.record_join(-100, 701, None, join_ts=time.time() - 600)
    consultas = []

    async def falso_lols(user_id, session):
        consultas.append(user_id)
        return None
    monkeypatch.setattr(rl.lols_det, "check", falso_lols)

    ctx = _ctx(db, _Bot(), _cfg())
    await rl.revisar_job(ctx)
    await rl.revisar_job(ctx)
    assert consultas == [701], "se estaría preguntando a lols en cada vuelta"


@pytest.mark.asyncio
async def test_un_cambio_de_nombre_se_caza_en_la_vuelta_siguiente(tmp_path, monkeypatch):
    """El caso entero: entra con nombre limpio y se pone el chino más tarde. Antes
    había que esperar a que venciera la espera de una hora; ahora cae a los 15 min."""
    db = _db(tmp_path)
    db.record_join(-100, 702, None, join_ts=time.time() - 600)
    nombre = ["Carlos"]

    class BotQueCambia(_Bot):
        async def get_chat_member(self, chat_id, user_id):
            return SimpleNamespace(chat=SimpleNamespace(id=chat_id, title="Domótica"),
                                   user=SimpleNamespace(
                                       id=user_id, is_bot=False, first_name=nombre[0],
                                       last_name=None, username=None))

    ctx = _ctx(db, BotQueCambia(), _cfg(lols_enabled=False, cas_enabled=False))
    aplicado = {}

    async def falso_apply(context, db_, cfg_, **kw):
        aplicado.update(kw)
    monkeypatch.setattr("src.handlers._apply_action", falso_apply)

    await rl.revisar_job(ctx)
    assert not aplicado, "con nombre latino no debe pasar nada"

    nombre[0] = "李大哥"                      # se lo cambia estando ya dentro
    await rl.revisar_job(ctx)
    assert aplicado.get("user_id") == 702
    assert aplicado["decision"].rule == "obvious_spam_profile"


@pytest.mark.asyncio
async def test_una_avalancha_no_convierte_una_vuelta_en_mil_llamadas(tmp_path, monkeypatch):
    db = _db(tmp_path)
    ahora = time.time()
    for uid in range(1000, 1000 + rl.MAX_NOMBRES_POR_CICLO + 40):
        db.record_join(-100, uid, None, join_ts=ahora - 600)
    leidos = []

    class BotQueCuenta(_Bot):
        async def get_chat_member(self, chat_id, user_id):
            leidos.append(user_id)
            return SimpleNamespace(user=SimpleNamespace(
                id=user_id, is_bot=False, first_name="Ana", last_name=None, username=None))

    ctx = _ctx(db, BotQueCuenta(), _cfg(lols_enabled=False, cas_enabled=False))
    await rl.revisar_job(ctx)
    assert len(leidos) == rl.MAX_NOMBRES_POR_CICLO


def test_el_tope_de_nombres_es_mucho_mayor_que_el_de_listas():
    """Si alguien los vuelve a igualar, es que ha perdido el porqué: uno es una
    llamada gratis de la Bot API y el otro una consulta a un tercero."""
    assert rl.MAX_NOMBRES_POR_CICLO > rl.MAX_POR_CICLO * 2


# ---------------------------------------------------------------------------
# El canal aparece cuando al spammer le conviene
#
# `RELECTURA_PERFIL_S` estuvo en 6 horas con este razonamiento: «un canal
# personal no aparece y desaparece, con mirarlo un par de veces basta». Es falso.
#
# Caso medido (10-ago-2026, Windows 10): «Simongirl40», nombre latino y foto de
# perfil normal, entró a las 09:49 y escribió a las 15:32 con el canal
# `财天下飞机进群结演员结算频道` en el perfil, que puntúa 160 de los 100
# necesarios. Su nombre es latino, así que la lectura del perfil dependía del
# presupuesto, y con relectura de 6 h cayó justo en la ventana muerta: se le
# cazó al escribir, no antes. El hueco no era del detector.
# ---------------------------------------------------------------------------

def test_el_perfil_se_relee_dentro_de_la_hora():
    assert rl.RELECTURA_PERFIL_S <= 3600, (
        "con relecturas más espaciadas, quien enlaza el canal después de entrar "
        "tiene horas de barra libre hasta que le toque")


def test_el_presupuesto_cubre_a_todos_los_de_la_ventana():
    """La cuenta que hace que lo anterior funcione: con el trabajo cada 15 min,
    el presupuesto por vuelta tiene que dar para releer a toda la ventana dentro
    del plazo. Medido en producción: 16-23 personas en la ventana."""
    vueltas_por_relectura = rl.RELECTURA_PERFIL_S / (15 * 60)
    capacidad = rl.MAX_PERFILES_POR_CICLO * vueltas_por_relectura
    assert capacidad >= 40, (
        f"solo caben {capacidad:.0f} lecturas por ciclo de relectura: "
        "no alcanza para la ventana real")


@pytest.mark.asyncio
async def test_al_mismo_perfil_se_vuelve_pasada_la_hora(tmp_path):
    """Comprobación de comportamiento: pasado el plazo, se relee."""
    ctx = SimpleNamespace(bot_data={rl._CLAVE_PRESUPUESTO: 50})
    assert rl._toca_leer_perfil(ctx, -100, 1) is True
    assert rl._toca_leer_perfil(ctx, -100, 1) is False
    ctx.bot_data[rl._CLAVE_PERFILES][(-100, 1)] = time.time() - rl.RELECTURA_PERFIL_S - 1
    assert rl._toca_leer_perfil(ctx, -100, 1) is True


def test_el_join_deja_constancia_de_lo_que_pudo_ver():
    """Sin esta traza no hay forma de saber, después, si alguien pasó porque su
    perfil estaba limpio o porque Telethon no llegó a leerlo. El join es el peor
    momento para resolver una entidad recién creada."""
    from pathlib import Path
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def on_chat_member(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    assert 'señales=%s canal=%s' in cuerpo


# ---------------------------------------------------------------------------
# La red midió nuestra ventana y esperó a que venciera
#
# Caso medido (15-ago-2026, Windows 10): el 7688429577 entró el 14-ago a las
# 08:26 CON EL PERFIL LIMPIO (la traza del join lo prueba: `señales=sí canal=-`,
# y con nombre Han el join banea o silencia, que no pasó). Dejó pasar la ventana
# de 24 h entera, se puso el nombre `六o0壹天` y el canal
# `财天下飞机进群结演员结算频道` ya FUERA de vigilancia, y escribió a las
# **29,6 h** de entrar. Lo cazó el chequeo del primer mensaje (440 pts), o sea
# la última línea de defensa: todo lo anterior había prescrito.
#
# Los tres casos de la misma red, en orden: 5,7 h → 15 h → 29,6 h. Se adaptan a
# lo que medimos. Contra eso, cualquier ventana corta es un plazo que se puede
# esperar; una semana obliga a mantener la cuenta dormida tanto que deja de
# salirles a cuenta. El coste se paga con dos cadencias, no con más llamadas.
# ---------------------------------------------------------------------------

def test_la_ventana_cubre_al_que_espero_a_que_venciera():
    assert rl.VENTANA_S >= 3 * 86400, (
        "el 7688429577 escribió a las 29,6 h justo porque la ventana era de 24: "
        "recortarla vuelve a regalar el truco de esperar")


def test_el_primer_dia_se_vigila_a_ritmo_caliente():
    """Dentro del primer día nada se espacia más que antes del cambio."""
    assert rl.FRESCO_S == 24 * 3600
    assert rl.RECHEQUEO_S <= 3600
    assert rl.RELECTURA_PERFIL_S <= 3600


@pytest.mark.asyncio
async def test_en_frio_el_nombre_se_sigue_mirando_en_cada_vuelta(tmp_path, monkeypatch):
    """La clave de que la semana entera sea vigilancia real: el nombre es gratis
    (Bot API), así que NO tiene ritmo frío. Quien se pone el nombre chino el
    día 3 cae en ≤15 min igual que si fuera el día 1."""
    db = _db(tmp_path)
    db.record_join(-100, 800, None, join_ts=time.time() - 3 * 86400)   # día 3
    nombre = ["Carlos"]

    class BotQueCambia(_Bot):
        async def get_chat_member(self, chat_id, user_id):
            return SimpleNamespace(chat=SimpleNamespace(id=chat_id, title="Domótica"),
                                   user=SimpleNamespace(
                                       id=user_id, is_bot=False, first_name=nombre[0],
                                       last_name=None, username=None))

    ctx = _ctx(db, BotQueCambia(), _cfg(lols_enabled=False, cas_enabled=False))
    aplicado = {}

    async def falso_apply(context, db_, cfg_, **kw):
        aplicado.update(kw)
    monkeypatch.setattr("src.handlers._apply_action", falso_apply)

    await rl.revisar_job(ctx)
    assert not aplicado, "con nombre latino no debe pasar nada"
    nombre[0] = "六o0壹天"
    await rl.revisar_job(ctx)
    assert aplicado.get("user_id") == 800, "en frío el nombre dejó de vigilarse"


def test_en_frio_las_lecturas_caras_se_espacian():
    """La contrapartida que hace sostenible la semana: Telethon y las listas
    van a ritmo frío pasado el primer día."""
    ctx = SimpleNamespace(bot_data={rl._CLAVE_PRESUPUESTO: 50})
    frio = int(rl.FRESCO_S + 3600)

    assert rl._toca_leer_perfil(ctx, -100, 1, frio) is True
    # A la media hora NO toca aún (en caliente sí tocaría a la hora)
    ctx.bot_data[rl._CLAVE_PERFILES][(-100, 1)] = time.time() - rl.RELECTURA_PERFIL_S - 1
    assert rl._toca_leer_perfil(ctx, -100, 1, frio) is False, \
        "en frío debe esperar RELECTURA_PERFIL_FRIA_S, no la caliente"
    ctx.bot_data[rl._CLAVE_PERFILES][(-100, 1)] = time.time() - rl.RELECTURA_PERFIL_FRIA_S - 1
    assert rl._toca_leer_perfil(ctx, -100, 1, frio) is True

    assert rl._toca_mirar(ctx, -100, 2, frio) is True
    ctx.bot_data[rl._CLAVE_CACHE][(-100, 2)] = time.time() - rl.RECHEQUEO_S - 1
    assert rl._toca_mirar(ctx, -100, 2, frio) is False
    ctx.bot_data[rl._CLAVE_CACHE][(-100, 2)] = time.time() - rl.RECHEQUEO_FRIO_S - 1
    assert rl._toca_mirar(ctx, -100, 2, frio) is True


def test_los_nombres_cubren_la_ventana_entera_medida():
    """142 callados medidos en 7 días: si el tope de nombres queda por debajo,
    los más antiguos (que son justo los que juegan a esperar) quedan sin mirar."""
    assert rl.MAX_NOMBRES_POR_CICLO >= 150


def test_el_presupuesto_aguanta_las_dos_cadencias():
    """La cuenta con la población medida: ~27 calientes (cada 1 h) + ~115 fríos
    (cada 6 h) ≈ 46 lecturas/h. El presupuesto por hora tiene que cubrirlo."""
    por_hora = rl.MAX_PERFILES_POR_CICLO * 4
    necesarias = 27 * (3600 / rl.RELECTURA_PERFIL_S) + 115 * (3600 / rl.RELECTURA_PERFIL_FRIA_S)
    assert por_hora >= necesarias * 0.9, (
        f"presupuesto {por_hora}/h para {necesarias:.0f} lecturas/h: el frío "
        "se degradaría mucho más de lo calculado")


# ---------------------------------------------------------------------------
# Disparador: alguien se cambia el nombre AHORA MISMO
#
# El barrido siempre llega con hasta 15 min de retraso. MTProto tiene
# `updateUserName`, que avisa en el momento; la Bot API NO entrega nada de eso
# (sus `chat_member` son cambios de ESTADO: entrar, salir, ban, promote).
#
# La documentación oficial NO dice para qué usuarios se entrega ese update, así
# que esto es defensa y experimento a la vez: si llega, el cambio de nombre se
# caza en segundos; si no llega, no se dispara nunca y el barrido sigue siendo
# la defensa. Lo que estos tests garantizan es que, llegue o no, no rompa nada
# y no invente criterios propios.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_el_disparo_caza_sin_esperar_al_barrido(tmp_path, monkeypatch):
    db = _db(tmp_path)
    db.record_join(-100, 900, None, join_ts=time.time() - 30 * 3600)   # día 2
    ctx = _ctx(db, _Bot(), _cfg(lols_enabled=False, cas_enabled=False))

    class BotChino(_Bot):
        async def get_chat_member(self, chat_id, user_id):
            return SimpleNamespace(chat=SimpleNamespace(id=chat_id, title="Domótica"),
                                   user=SimpleNamespace(
                                       id=user_id, is_bot=False, first_name="六o0壹天",
                                       last_name=None, username=None))

    ctx.bot = BotChino()
    aplicado = {}

    async def falso_apply(context, db_, cfg_, **kw):
        aplicado.update(kw)
    monkeypatch.setattr("src.handlers._apply_action", falso_apply)

    assert await rl.revisar_ahora(ctx, 900) is True
    assert aplicado["decision"].rule == "obvious_spam_profile"


@pytest.mark.asyncio
async def test_a_quien_no_vigilamos_no_se_le_toca(tmp_path):
    """Llegarán updates de gente que no está en ningún grupo nuestro."""
    db = _db(tmp_path)
    ctx = _ctx(db, _Bot(), _cfg())
    assert await rl.revisar_ahora(ctx, 12345) is False


@pytest.mark.asyncio
async def test_quien_ya_escribio_no_entra_por_esta_via(tmp_path):
    """La vigilancia es para los callados; al que participa lo juzgan sus
    mensajes, no un cambio de nombre."""
    db = _db(tmp_path)
    db.record_join(-100, 901, None, join_ts=time.time() - 3600)
    db.record_message(-100, 901, None)
    ctx = _ctx(db, _Bot(), _cfg())
    assert await rl.revisar_ahora(ctx, 901) is False


@pytest.mark.asyncio
async def test_una_rafaga_de_cambios_no_dispara_una_rafaga_de_lecturas(tmp_path):
    """Si juegan a cambiarse el nombre en bucle, no vamos a leerles el perfil
    por Telethon una vez por cambio."""
    db = _db(tmp_path)
    db.record_join(-100, 902, None, join_ts=time.time() - 3600)
    ctx = _ctx(db, _Bot(), _cfg(lols_enabled=False, cas_enabled=False))
    leidos = []

    class BotQueCuenta(_Bot):
        async def get_chat_member(self, chat_id, user_id):
            leidos.append(user_id)
            return SimpleNamespace(chat=SimpleNamespace(id=chat_id, title="Domótica"),
                                   user=SimpleNamespace(id=user_id, is_bot=False,
                                                        first_name="Ana", last_name=None,
                                                        username=None))

    ctx.bot = BotQueCuenta()
    for _ in range(10):
        await rl.revisar_ahora(ctx, 902)
    assert len(leidos) == 1, "el freno por persona no está funcionando"


@pytest.mark.asyncio
async def test_un_baneado_no_se_revisa_otra_vez(tmp_path):
    db = _db(tmp_path)
    db.record_join(-100, 903, None, join_ts=time.time() - 3600)
    db.add_ban(user_id=903, reason="x", rule="y", banned_in_chat=-100)
    ctx = _ctx(db, _Bot(), _cfg())
    assert await rl.revisar_ahora(ctx, 903) is False


@pytest.mark.asyncio
async def test_un_fallo_no_propaga_al_listener(tmp_path):
    """Lo llama un handler de Telethon: si esto lanza, se cae el listener."""
    class DBRota:
        def is_banned(self, uid):
            return False

        def vigilancia_de(self, uid, desde):
            raise RuntimeError("base caída")

    ctx = _ctx(DBRota(), _Bot(), _cfg())
    assert await rl.revisar_ahora(ctx, 904) is False


def test_el_disparo_no_tiene_criterios_propios():
    """Reutiliza `_revisar_perfil`: si tuviera su propia lógica, habría dos
    varas de medir y la del disparo se quedaría atrás en cada cambio."""
    from pathlib import Path
    fuente = Path("src/recien_llegados.py").read_text()
    i = fuente.index("async def revisar_ahora(")
    cuerpo = fuente[i:]
    assert "_revisar_perfil" in cuerpo
    for propio in ("_is_obvious_spam_profile", "personal_channel", "Decision("):
        assert propio not in cuerpo, f"el disparo no puede decidir por su cuenta ({propio})"


def test_el_listener_no_puede_tumbar_el_bot():
    from pathlib import Path
    fuente = Path("src/telethon_bridge.py").read_text()
    i = fuente.index("async def _on_user_name(")
    bloque = fuente[i:i + 900]
    assert "except Exception" in bloque
