"""Modo suave: silenciar para siempre en vez de expulsar.

Un falso positivo con mute se deshace sin que la persona llegue a enterarse; uno
con ban la obliga a pedir entrar otra vez, y mucha gente no vuelve. En un proyecto
cuya primera regla es «falsos positivos > falsos negativos», poder elegir eso por
grupo tiene sentido.

Lo que NO se ablanda son las reglas duras (CAS, lols, ban federado, reaction
farming, destino confeso): ahí no hay duda que proteger, son spammers confirmados,
y dejarlos dentro mudos es dejarlos dentro.
"""
from types import SimpleNamespace

from src.db import DB
from src.handlers import HARD_RULES_BAN, _modo_suave


def _db(tmp_path) -> DB:
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(-100, "G", "supergroup", True, True, True)
    return db


def _cfg(soft=False):
    return SimpleNamespace(soft_ban=soft)


def test_apagado_por_defecto(tmp_path):
    """Nadie se encuentra el comportamiento cambiado sin haberlo pedido."""
    db = _db(tmp_path)
    db.ensure_chat_settings(-100)
    assert _modo_suave(db, -100, _cfg(soft=False)) is False


def test_null_hereda_del_env(tmp_path):
    """Regla del proyecto para todo ajuste nuevo: NULL = «no se ha decidido aquí».
    Con un default 0, quien lo tuviera activo por .env se quedaba sin él al
    actualizar, y en silencio."""
    db = _db(tmp_path)
    db.ensure_chat_settings(-100)
    assert _modo_suave(db, -100, _cfg(soft=True)) is True


def test_el_ajuste_del_chat_manda_sobre_el_env(tmp_path):
    db = _db(tmp_path)
    db.ensure_chat_settings(-100)
    db.update_chat_setting(-100, "soft_ban", 0)
    assert _modo_suave(db, -100, _cfg(soft=True)) is False
    db.update_chat_setting(-100, "soft_ban", 1)
    assert _modo_suave(db, -100, _cfg(soft=False)) is True


def test_un_fallo_de_lectura_cae_al_env(tmp_path):
    """Un ajuste cosmético jamás puede impedir que se ejecute una acción."""
    class Rota:
        def get_chat_settings(self, cid):
            raise RuntimeError("base ocupada")
    assert _modo_suave(Rota(), -100, _cfg(soft=True)) is True
    assert _modo_suave(Rota(), -100, _cfg(soft=False)) is False


def test_las_reglas_duras_no_se_ablandan():
    """Son spammers confirmados por una lista externa o por la federación: dejarlos
    dentro mudos es dejarlos dentro."""
    for regla in ("cas_match", "lols_match", "federation_known_ban",
                  "reaction_farming", "link_target_spam"):
        assert regla in HARD_RULES_BAN


def test_el_handler_respeta_las_reglas_duras():
    """La condición está en el handler; si alguien la quita, este test lo dice."""
    from pathlib import Path
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("_modo_suave(db, chat_id, cfg)")
    assert "HARD_RULES_BAN" in fuente[i:i + 200]


def test_es_sincronizable_y_llega_al_panel():
    """Si no está en ALLOWED, `update_chat_setting` lo ignora en silencio y el
    botón del panel parecería no hacer nada."""
    from src.db import DB as _DB
    import inspect
    assert '"soft_ban"' in inspect.getsource(_DB.update_chat_setting)
    from src.config_panel import _TOGGLE_FIELDS
    assert "soft_ban" in _TOGGLE_FIELDS
