"""Salir y volver a entrar no puede borrar el nivel ganado.

Caso real (23-ago-2026, Domótica). Un miembro **desde julio de 2022**, con 14
mensajes y trust 74, intentó borrar un foro del grupo, resultó que los foros van
integrados y se salió del grupo entero sin querer. Al volver a unirse se
encontró la verificación otra vez y escribió al admin: *«el bot me está pidiendo
que verifique todo el tiempo o me banea y ya no sé dónde ni cómo hacerlo»*.

El bot no le baneó nunca (verificó en 2 min 40 s), pero la queja era legítima: a
alguien con cuatro años en el grupo se le trató como a un desconocido.

La causa: `on_join` miraba el perfil de **Telegram** (`_is_very_legit_profile`:
foto, antigüedad de la cuenta) y NUNCA el historial **en el grupo**. Y la marca
de «este ya se verificó» no existía en ninguna parte, porque
`pending_verifications` se vacía al verificar.

Lo que NO cambia: los detectores de perfil y de mensaje se aplican enteros a
quien reentra. Lo único que se salta es el botón, que además no protege de nada
(un bot lo pulsa en 3 segundos, medido en esta misma instalación).
"""
import time
from types import SimpleNamespace as NS

import pytest

from src import verification
from src.db import DB


def _db(tmp_path) -> DB:
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(-100, "Domótica", "supergroup", True, True, True)
    return db


# ------------------------------------------------ la marca de «ya me verifiqué»

def test_la_verificacion_deja_constancia(tmp_path):
    """Antes no se guardaba en ningún sitio: `pending_verifications` se vacía."""
    db = _db(tmp_path)
    db.record_join(-100, 1, "ana", join_ts=time.time())
    assert db.ya_verificado(-100, 1) is False
    db.marcar_verificado(-100, 1)
    assert db.ya_verificado(-100, 1) is True


def test_la_marca_es_por_chat(tmp_path):
    """Verificarse en Domótica no da paso libre en Windows 10."""
    db = _db(tmp_path)
    db.upsert_bot_chat(-200, "Windows 10", "supergroup", True, True, True)
    db.record_join(-100, 1, None, join_ts=time.time())
    db.record_join(-200, 1, None, join_ts=time.time())
    db.marcar_verificado(-100, 1)
    assert db.ya_verificado(-100, 1) is True
    assert db.ya_verificado(-200, 1) is False


def test_la_marca_sobrevive_a_salir_y_volver(tmp_path):
    """`record_join` no puede pisarla: es justo el caso para el que existe."""
    db = _db(tmp_path)
    db.record_join(-100, 1, None, join_ts=time.time() - 86400)
    db.marcar_verificado(-100, 1)
    db.record_join(-100, 1, None, join_ts=time.time())        # reentra
    assert db.ya_verificado(-100, 1) is True


# --------------------------------------------------- quién se libra del botón

def test_quien_ya_se_verifico_no_repite(tmp_path):
    db = _db(tmp_path)
    db.record_join(-100, 1, None, join_ts=time.time())
    db.marcar_verificado(-100, 1)
    de_casa, motivo = verification._ya_es_de_casa(db, -100, 1)
    assert de_casa and "verificó" in motivo


def test_con_historial_de_mensajes_tampoco(tmp_path):
    """Cubre a quien se verificó ANTES de que existiera la marca, y a quien ya
    estaba en el grupo cuando llegó el bot."""
    db = _db(tmp_path)
    db.record_join(-100, 2, None, join_ts=time.time())
    for _ in range(verification.MIN_MSGS_DE_CASA):
        db.record_message(-100, 2, None)
    de_casa, motivo = verification._ya_es_de_casa(db, -100, 2)
    assert de_casa and "mensajes previos" in motivo


def test_un_recien_llegado_de_verdad_si_pasa_el_gate(tmp_path):
    db = _db(tmp_path)
    db.record_join(-100, 3, None, join_ts=time.time())
    assert verification._ya_es_de_casa(db, -100, 3)[0] is False


def test_uno_o_dos_mensajes_no_bastan(tmp_path):
    """Un spammer que suelta un «hola» y se sale no compra el paso libre."""
    db = _db(tmp_path)
    db.record_join(-100, 4, None, join_ts=time.time())
    for _ in range(verification.MIN_MSGS_DE_CASA - 1):
        db.record_message(-100, 4, None)
    assert verification._ya_es_de_casa(db, -100, 4)[0] is False


def test_a_quien_no_conocemos_de_nada(tmp_path):
    db = _db(tmp_path)
    assert verification._ya_es_de_casa(db, -100, 999)[0] is False


def test_una_base_ilegible_no_abre_la_mano(tmp_path):
    """Ante la duda, verificación normal."""
    class Rota:
        def get_seen(self, c, u):
            raise RuntimeError("base caída")
    assert verification._ya_es_de_casa(Rota(), -100, 1)[0] is False


# ------------------------------------------------- el nivel ganado se conserva

def test_reentrar_no_borra_la_antiguedad_ni_los_mensajes(tmp_path):
    """El caso literal: 4 años y 14 mensajes tienen que seguir ahí al volver."""
    db = _db(tmp_path)
    hace_4_anios = time.time() - 1500 * 86400
    db.record_join(-100, 5, "joakin", join_ts=hace_4_anios)
    for _ in range(14):
        db.record_message(-100, 5, "joakin")
    antes = db.user_trust_score(-100, 5)

    db.record_join(-100, 5, "joakin", join_ts=time.time())     # se sale y vuelve
    fila = db.get_seen(-100, 5)
    assert fila["msg_count"] == 14, "perdió los mensajes al reentrar"
    assert fila["first_seen_ts"] <= hace_4_anios + 1, "perdió la antigüedad"
    assert db.user_trust_score(-100, 5) >= antes, "perdió confianza por reentrar"


def test_el_trust_de_ese_miembro_supera_el_umbral(tmp_path):
    """Comprobación del caso medido: 14 mensajes y 1500 días dan 74, o sea que ya
    estaba por encima del umbral de 70 y aun así pasó por el gate. El gate no
    miraba el trust: ese era el fallo."""
    db = _db(tmp_path)
    db.record_join(-100, 6, None, join_ts=time.time() - 1500 * 86400)
    for _ in range(14):
        db.record_message(-100, 6, None)
    assert db.user_trust_score(-100, 6) >= 70


# ------------------------------------------------------- lo que NO se relaja

def test_el_skip_no_toca_la_deteccion():
    """Solo se salta el botón. Los detectores de perfil van ANTES en el flujo del
    join y siguen aplicándose a quien reentra."""
    from pathlib import Path
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def on_chat_member(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    # `await …on_join(`, la LLAMADA: el nombre suelto sale antes en dos
    # comentarios y hacía que el test midiera otra cosa.
    orden = [cuerpo.index(x) for x in
             ("_is_obvious_spam_profile", "_mirar_canal_personal",
              "await verification.on_join(")]
    assert orden == sorted(orden), "el skip no puede adelantarse a los detectores"


def test_un_baneado_en_federacion_no_se_libra():
    """Reentrar estando baneado se resuelve antes de llegar a la verificación."""
    from pathlib import Path
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def on_chat_member(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    assert cuerpo.index("db.is_banned(user.id)") < cuerpo.index("verification.on_join")


@pytest.mark.asyncio
async def test_el_gate_se_salta_de_verdad_en_on_join(tmp_path, monkeypatch):
    """Comportamiento, no texto: un conocido no acaba muteado ni con botón."""
    db = _db(tmp_path)
    db.record_join(-100, 7, "ana", join_ts=time.time() - 86400)
    db.marcar_verificado(-100, 7)
    db.ensure_chat_settings(-100)
    db.update_chat_setting(-100, "verification_enabled", 1)

    permisos = []
    pendientes = []
    monkeypatch.setattr(db, "add_pending_verification",
                        lambda *a, **k: pendientes.append(a))

    async def _restrict(chat_id, user_id, permissions, **kw):
        permisos.append(permissions)

    ctx = NS(
        bot=NS(restrict_chat_member=_restrict,
               send_message=lambda *a, **k: None),
        bot_data={"db": db, "cfg": NS(shadow=False)},
        application=NS(job_queue=None),
    )
    chat = NS(id=-100, title="Domótica")
    user = NS(id=7, username="ana", first_name="Ana", last_name=None, is_bot=False)

    await verification.on_join(None, ctx, chat, user, prefetched_sig=None)

    assert not pendientes, "no debería quedar pendiente de verificar"
    assert permisos, "debería haberse desmuteado"
    assert permisos[-1] is verification.VERIFIED_PERMISSIONS
