"""Escribir un @usuario no puede acabar avisando a otra persona.

Caso reportado (7-ago-2026): al poner un warn, el bot mencionó a alguien distinto
del objetivo. El mecanismo estaba en el mapa `@usuario -> id`: se resolvía el
conflicto en un solo sentido (mismo alias, otra persona) pero los alias VIEJOS no
se borraban nunca. Medido en la base de datos real:

    @anthony10a -> 6683352880, que hoy es @Milagros90b
    @hm_atwork  -> 1390010913, que hoy es @SAxELvCwUnpRC

Así que `/warn @anthony10a` resolvía a esa persona y el bot publicaba el aviso
mencionando su @usuario ACTUAL: escribías un nombre y salía otro, y el warn caía
sobre quien no era.

Dos defensas, porque una sola no basta:
  1. Al ver a alguien con su @usuario se borran sus alias anteriores. Arregla a
     quien el bot vuelve a ver.
  2. Antes de actuar se contrasta con Telegram. Cubre a quien no ha vuelto a
     aparecer, que es justo el caso peligroso.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db import DB


def test_cambiarse_el_nombre_borra_el_alias_viejo(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    db.remember_username("anthony10a", 555)
    assert db.resolve_username("anthony10a") == 555

    db.remember_username("milagros90b", 555)          # se cambia el nombre
    assert db.resolve_username("anthony10a") is None, (
        "el alias viejo sigue apuntando a esa persona: un /warn @anthony10a "
        "acabaría avisando a @milagros90b")
    assert db.resolve_username("milagros90b") == 555


def test_si_otra_persona_coge_el_alias_libre_se_le_asigna(tmp_path):
    """El sentido que ya funcionaba y no se puede romper."""
    db = DB(str(tmp_path / "t.db"))
    db.remember_username("pepe", 555)
    db.remember_username("otro", 555)      # 555 lo libera
    db.remember_username("pepe", 999)      # 999 lo coge
    assert db.resolve_username("pepe") == 999


def test_una_persona_solo_tiene_un_alias(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    for nombre in ("uno", "dos", "tres"):
        db.remember_username(nombre, 555)
    with db._cur() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM username_map WHERE user_id=555").fetchone()["n"]
    assert n == 1, f"quedan {n} alias para la misma persona"


@pytest.mark.asyncio
async def test_se_contrasta_con_telegram_antes_de_actuar(tmp_path):
    """Aunque el mapa esté desfasado, no se actúa sobre la persona equivocada."""
    from src import admin
    db = DB(str(tmp_path / "t.db"))
    with db._cur() as c:      # alias obsoleto metido a mano, como los reales
        c.execute("INSERT INTO username_map (username_lower, user_id, updated_at) "
                  "VALUES ('anthony10a', 555, 0)")

    ctx = MagicMock()
    ctx.args = ["anthony10a", "motivo"]
    # Telegram dice que esa persona hoy se llama de otra forma
    ctx.bot.get_chat = AsyncMock(return_value=MagicMock(username="Milagros90b"))
    msg = MagicMock()
    msg.reply_to_message = None
    msg.entities = None
    upd = MagicMock()
    upd.effective_message = msg

    uid, _resto, err = await admin._resolve_target_user(upd, ctx, db)
    assert uid is None, "actuó sobre la persona equivocada"
    assert err and "Milagros90b" in err, "no dice quién es realmente ese id"
    # y aprovecha para corregir el mapa
    assert db.resolve_username("anthony10a") is None


@pytest.mark.asyncio
async def test_si_telegram_no_responde_se_sigue_adelante(tmp_path):
    """None significa «no lo sé», no «no coincide»: bloquear un /ban legítimo
    porque Telegram no contesta sería peor que el problema."""
    from src import admin
    db = DB(str(tmp_path / "t.db"))
    db.remember_username("pepe", 555)
    ctx = MagicMock()
    ctx.args = ["pepe"]
    ctx.bot.get_chat = AsyncMock(side_effect=RuntimeError("sin red"))
    msg = MagicMock()
    msg.reply_to_message = None
    msg.entities = None
    upd = MagicMock()
    upd.effective_message = msg
    uid, _r, err = await admin._resolve_target_user(upd, ctx, db)
    assert uid == 555 and err is None


def test_el_nombre_se_refresca_en_todos_los_grupos(tmp_path):
    """`record_message` solo actualiza el chat donde la persona escribe, así que
    quien participa en un grupo y no en otro se quedaba con DOS nombres según
    dónde se le mirara, y los avisos del segundo usaban el viejo. Medido en la
    base de datos real: 6683352880 constaba a la vez como @Milagros90b y
    @Anthony10a según el chat."""
    db = DB(str(tmp_path / "t.db"))
    for cid in (-100, -200):
        db.upsert_bot_chat(cid, "G", "supergroup", True, True, True)
        db.record_message(cid, 555, "Anthony10a")

    db.record_message(-100, 555, "Milagros90b")   # se cambia el nombre y escribe
    db.remember_username("Milagros90b", 555)

    with db._cur() as c:
        nombres = {f["username"] for f in
                   c.execute("SELECT username FROM seen_users WHERE user_id=555")}
    assert nombres == {"Milagros90b"}, f"convive con nombres distintos: {nombres}"
