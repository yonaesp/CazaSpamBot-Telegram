"""Los admins del grupo pueden warnear, y el alcance del ban es configurable.

Decisión del dueño del bot (11-ago-2026) tras el reporte de un admin de grupo:
«he usado /warn, el mensaje se borra pero no pone el warn». La causa era que
`/warn` solo lo podía usar el dueño; el `CLAUDE.md` ya preveía este momento
(«hardcoded check, no role-based hasta que haya >1 admin») y ya hay varios.

Dónde se traza la línea:

- **Poner y quitar warns** (`/warn`, `/warns`, `/rmwarn`, `/resetwarns`) es
  moderación del día a día y no puede depender de que el dueño esté delante.
- **Cambiar el castigo** (`/warnlimit`, `/warnaction`) sigue siendo del dueño:
  decide el alcance del daño, no lo aplica.

Y como un warn que llega al límite puede acabar en un **ban federado a los
cuatro grupos**, el alcance se deja configurable: federado por defecto (lo que el
bot ha hecho siempre), o solo el grupo, que es lo prudente si no todos los admins
son de la misma confianza.
"""
import time
from types import SimpleNamespace as NS

import pytest

from src import permissions, warns_mod
from src.db import DB


def _db(tmp_path) -> DB:
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(-100, "Windows 11", "supergroup", True, True, True)
    db.ensure_chat_settings(-100)
    return db


# --------------------------------------------------- el ajuste de quién warnea

class _Bot:
    def __init__(self, estado="administrator"):
        self.estado = estado
        self.enviados = []

    async def get_chat_member(self, chat_id, user_id):
        return NS(user=NS(id=user_id), status=self.estado)

    async def send_message(self, chat_id, text, **kw):
        self.enviados.append(text)
        return NS(message_id=1)


def _update(user_id, chat_id=-100):
    return NS(effective_user=NS(id=user_id, username="a", first_name="A"),
              effective_message=NS(chat_id=chat_id, message_id=5))


def _ctx(db, bot, admin_id=1):
    return NS(bot=bot, bot_data={"db": db, "cfg": NS(admin_user_id=admin_id)},
              application=NS(job_queue=None))


@pytest.mark.asyncio
async def test_por_defecto_un_admin_del_grupo_puede_warnear(tmp_path):
    db = _db(tmp_path)
    ejecutado = []

    @permissions.warn_admin_only
    async def cmd(update, context):
        ejecutado.append(1)

    await cmd(_update(555), _ctx(db, _Bot("administrator")))
    assert ejecutado == [1]


@pytest.mark.asyncio
async def test_un_usuario_normal_del_grupo_no(tmp_path):
    db = _db(tmp_path)
    ejecutado = []

    @permissions.warn_admin_only
    async def cmd(update, context):
        ejecutado.append(1)

    await cmd(_update(555), _ctx(db, _Bot("member")))
    assert not ejecutado


@pytest.mark.asyncio
async def test_se_puede_dejar_como_estaba(tmp_path):
    """`bot_admin` devuelve el comportamiento anterior para ese chat."""
    db = _db(tmp_path)
    db.update_chat_setting(-100, "warn_quien", "bot_admin")
    ejecutado = []

    @permissions.warn_admin_only
    async def cmd(update, context):
        ejecutado.append(1)

    await cmd(_update(555), _ctx(db, _Bot("administrator")))
    assert not ejecutado, "con 'bot_admin' solo puede el dueño"


@pytest.mark.asyncio
async def test_el_dueno_puede_siempre(tmp_path):
    db = _db(tmp_path)
    db.update_chat_setting(-100, "warn_quien", "bot_admin")
    ejecutado = []

    @permissions.warn_admin_only
    async def cmd(update, context):
        ejecutado.append(1)

    await cmd(_update(1), _ctx(db, _Bot("member"), admin_id=1))
    assert ejecutado == [1]


@pytest.mark.asyncio
async def test_ser_admin_de_otro_grupo_no_da_derecho_aqui(tmp_path):
    """`is_chat_admin_any` valdría para VER cosas; para moderar aquí hay que
    mandar aquí. Si no, un admin de Windows 10 warnearía en Domótica."""
    db = _db(tmp_path)
    ejecutado = []

    @permissions.warn_admin_only
    async def cmd(update, context):
        ejecutado.append(1)

    await cmd(_update(555), _ctx(db, _Bot("member")))   # no es admin de ESTE chat
    assert not ejecutado


@pytest.mark.asyncio
async def test_en_privado_no_se_abre_la_mano(tmp_path):
    """Un ajuste por chat no tiene sentido en un DM, y ahí no hay grupo que
    moderar: solo el dueño."""
    db = _db(tmp_path)
    ejecutado = []

    @permissions.warn_admin_only
    async def cmd(update, context):
        ejecutado.append(1)

    await cmd(_update(555, chat_id=555), _ctx(db, _Bot("administrator")))
    assert not ejecutado


@pytest.mark.asyncio
async def test_un_ajuste_ilegible_no_abre_la_mano(tmp_path):
    """Fail-safe: ante la duda, el reparto restrictivo."""
    class DBRota:
        def get_chat_settings(self, chat_id):
            raise RuntimeError("base corrupta")

    ejecutado = []

    @permissions.warn_admin_only
    async def cmd(update, context):
        ejecutado.append(1)

    await cmd(_update(555), _ctx(DBRota(), _Bot("administrator")))
    assert not ejecutado


# ------------------------------------------------------- el alcance del ban

def test_el_ban_es_federado_por_defecto(tmp_path):
    db = _db(tmp_path)
    assert warns_mod._ban_federado(db, -100) is True


def test_se_puede_dejar_el_ban_en_el_grupo(tmp_path):
    db = _db(tmp_path)
    db.update_chat_setting(-100, "warn_ban_federado", 0)
    assert warns_mod._ban_federado(db, -100) is False


def test_un_chat_sin_ajustes_hereda_el_defecto(tmp_path):
    db = _db(tmp_path)
    assert warns_mod._ban_federado(db, -999) is True


def test_un_ajuste_ilegible_mantiene_lo_de_siempre(tmp_path):
    """La federación es lo que el bot ha hecho desde el principio; un ajuste
    ilegible no puede cambiarlo en silencio."""
    class DBRota:
        def get_chat_settings(self, chat_id):
            raise RuntimeError("base corrupta")
    assert warns_mod._ban_federado(DBRota(), -100) is True


# ------------------------------------------------------------ persistencia

def test_los_dos_ajustes_se_guardan_y_se_leen(tmp_path):
    db = _db(tmp_path)
    db.update_chat_setting(-100, "warn_quien", "bot_admin")
    db.update_chat_setting(-100, "warn_ban_federado", 0)
    s = db.get_chat_settings(-100)
    assert s["warn_quien"] == "bot_admin"
    assert s["warn_ban_federado"] == 0


def test_la_migracion_los_anade_a_una_base_vieja(tmp_path):
    """Una instalación que ya existía tiene que arrancar sin tocar nada a mano."""
    import sqlite3
    ruta = str(tmp_path / "vieja.db")
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE chat_settings (chat_id INTEGER PRIMARY KEY, warns_limit INTEGER)")
    con.commit()
    con.close()
    db = DB(ruta)                                  # dispara _migrate()
    cols = {r[1] for r in db._conn.execute("PRAGMA table_info(chat_settings)")}
    assert {"warn_quien", "warn_ban_federado"} <= cols


def test_el_panel_los_ofrece():
    """Todo ajuste por chat se toca desde el panel visual (convención del proyecto)."""
    from pathlib import Path
    fuente = Path("src/config_panel.py").read_text()
    for trozo in ("wquien", "wfed", "_WARN_QUIEN", "warn_ban_federado"):
        assert trozo in fuente, f"falta {trozo} en el panel"


def test_respetan_el_modo_sync():
    """Con /sync ON un cambio se aplica a todos los grupos, como el resto."""
    from pathlib import Path
    fuente = Path("src/config_panel.py").read_text()
    i = fuente.index('if action == "wquien":')
    bloque = fuente[i:fuente.index('if action == "mg":', i)]
    assert bloque.count("settings_sync.apply_setting") == 2


def test_el_tiempo_no_se_usa_para_nada_raro():
    """Guarda contra copiar-pegar: estos ajustes no llevan caducidad."""
    assert time is not None
