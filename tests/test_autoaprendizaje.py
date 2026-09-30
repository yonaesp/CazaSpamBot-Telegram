"""El bot aprende solo, sin IA externa (decisión del admin, 30-sep-2026)."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import autoaprendizaje as A
from src.db import DB

CHAT = -1001190184646


@pytest.fixture
def db(tmp_path):
    return DB(str(tmp_path / "t.db"))


NORMAL = "Os dejó instalar la KB5124010 sin problemas? a mí se me queda al 99 %"


# --- ejemplos legítimos automáticos -------------------------------------------

def test_guarda_el_mensaje_normal_de_alguien_asentado(db):
    assert A.guardar_ham_si_procede(db, CHAT, 1, NORMAL, trust=80)
    assert db.recent_sample_texts(label="ham", limit=10)


def test_no_guarda_a_desconocidos(db):
    assert not A.guardar_ham_si_procede(db, CHAT, 1, NORMAL, trust=69)


def test_no_guarda_enlaces_menciones_ni_reenvios(db):
    """Es justo lo que metería un spammer con cuenta veterana para «limpiarse»."""
    for txt in (NORMAL + " https://x.com", NORMAL + " @canaldeofertas", NORMAL + " t.me/x"):
        assert not A.guardar_ham_si_procede(db, CHAT, 1, txt, trust=90)
    assert not A.guardar_ham_si_procede(db, CHAT, 1, NORMAL, trust=90, reenviado=True)


def test_no_guarda_mensajes_cortos(db):
    assert not A.guardar_ham_si_procede(db, CHAT, 1, "ok gracias", trust=90)


def test_uno_por_persona_y_dia(db):
    assert A.guardar_ham_si_procede(db, CHAT, 1, NORMAL, trust=90)
    assert not A.guardar_ham_si_procede(db, CHAT, 1, NORMAL + " y otra cosa más", trust=90)
    assert A.guardar_ham_si_procede(db, CHAT, 2, NORMAL + " y otra cosa más", trust=90)


def test_tope_diario(db, monkeypatch):
    monkeypatch.setattr(A, "HAM_MAX_DIA", 3)
    for uid in range(10):
        A.guardar_ham_si_procede(db, CHAT, uid, f"{NORMAL} variante número {uid}", trust=90)
    assert db.muestras_auto_desde("ham", time.time() - 86400) == 3


def test_si_lo_banean_se_olvida_lo_aprendido_de_el(db):
    A.guardar_ham_si_procede(db, CHAT, 7, NORMAL, trust=90)
    A.olvidar_ham_automatico(db, 7)
    assert not db.recent_sample_texts(label="ham", limit=10)


def test_lo_que_marco_el_admin_no_se_olvida_solo(db):
    db.add_sample(text_norm="algo legítimo marcado a mano", text_hash="h", label="ham",
                  added_by=14573395, chat_id=CHAT, source_user=7)
    A.olvidar_ham_automatico(db, 7)
    assert db.recent_sample_texts(label="ham", limit=10)


# --- ejemplos de spam de los bans seguros --------------------------------------

SPAM = "📙 ADOBE REDEEM CODE ( 1month - 12months ) warranty full, office pro plus"


def test_aprende_de_un_ban_por_contenido_con_evidencia_fuerte(db):
    assert A.aprender_spam_de_ban(db, CHAT, 5, SPAM, "commercial_ad", 155)


def test_aprende_con_lista_externa_aunque_puntue_menos(db):
    assert A.aprender_spam_de_ban(db, CHAT, 5, SPAM, "commercial_ad+cas_match", 120)


def test_no_aprende_de_senales_de_forma_caso_kleo(db):
    """150 exactos solo con forma: el caso Kleo, una pregunta legítima."""
    assert not A.aprender_spam_de_ban(db, CHAT, 5, SPAM, "forward_first_msg+first_msg_media", 150)


def test_no_aprende_de_bans_por_perfil(db):
    """Un «hola» de alguien con el nombre en otro alfabeto no es un ejemplo de spam."""
    assert not A.aprender_spam_de_ban(db, CHAT, 5, "hola buenas a todos, qué tal va", "obvious_spam_profile", 200)


def test_no_se_realimenta_de_lo_ya_aprendido(db):
    assert not A.aprender_spam_de_ban(db, CHAT, 5, SPAM, "learned_similarity", 200)


def test_al_desbanear_se_olvida_el_spam_aprendido_solo(db):
    A.aprender_spam_de_ban(db, CHAT, 5, SPAM, "commercial_ad", 155)
    A.olvidar_spam_automatico(db, 5)
    assert not db.recent_sample_texts(label="spam", limit=10)


# --- propuestas de frases ------------------------------------------------------

def test_una_frase_de_un_solo_spam_no_se_propone(db):
    """Medido el 30-sep-2026: entre 37 spams reales solo UNA frase se repetía
    («al mes», lenguaje corriente). Proponer frases de un único spam era proponer
    falsos positivos: a una pregunta normal le sugería «no me aparece»."""
    assert A.elegir(db, ["Buenas, alguien sabe por qué no me aparece el PC en la red local?"]) == []
    assert A.elegir(db, [SPAM]) == []


def test_una_frase_repetida_en_otro_spam_si(db):
    db.add_sample(text_norm="vendo cuentas verificadas binance baratas", text_hash="x",
                  label="spam", added_by=0, chat_id=CHAT, source_user=9)
    nuevo = "🔥 Tengo cuentas verificadas binance con garantía, escríbeme"
    terms = [e["term"] for e in A.elegir(db, [nuevo])]
    assert any("verificadas binance" in x for x in terms), terms


def test_no_propone_lo_que_ya_esta_cubierto(db):
    """«redeem code» ya está en la lista en inglés: no se vuelve a proponer."""
    db.add_sample(text_norm="adobe redeem code barato", text_hash="x", label="spam",
                  added_by=0, chat_id=CHAT, source_user=9)
    assert all("redeem code" not in e["term"] for e in A.elegir(db, [SPAM]))


def test_sin_confirmacion_no_se_aprende_nada(db, monkeypatch):
    """Un ban manual solo PROPONE: se banea también por insultar."""
    enviados = []

    async def _send(**kw):
        enviados.append(kw)
    db.guardar_mensaje_reciente(CHAT, 5, 1, SPAM)
    ctx = SimpleNamespace(bot=SimpleNamespace(send_message=_send), bot_data={})
    cfg = SimpleNamespace(admin_notify_chat_id=14573395, admin_user_id=14573395)
    assert asyncio.run(A.proponer_reglas(ctx, db, cfg, 5, CHAT, motivo="x"))
    assert enviados and not db.recent_sample_texts(label="spam", limit=10)


def test_el_boton_confirma_y_aprende(db):
    db.set_text_pref("rprop_abcd", json.dumps({"u": 5, "c": CHAT, "terms": [], "texts": [SPAM]}))
    respuestas = []

    async def _answer(*a, **k):
        respuestas.append(a)

    async def _edit(*a, **k):
        pass
    q = SimpleNamespace(data="rprop:m:abcd", from_user=SimpleNamespace(id=14573395),
                        answer=_answer, edit_message_text=_edit,
                        message=SimpleNamespace(text_html="x", text="x"))
    ctx = SimpleNamespace(bot_data={"cfg": SimpleNamespace(admin_user_id=14573395), "db": db})
    asyncio.run(A.on_callback(SimpleNamespace(callback_query=q), ctx))
    assert db.recent_sample_texts(label="spam", limit=10)


def test_callback_data_cabe_en_64_bytes():
    assert len("rprop:t:abcdef01:2".encode()) <= 64


def test_esta_enganchado_en_los_cuatro_sitios():
    h = Path("src/handlers.py").read_text(encoding="utf-8")
    f = Path("src/federation.py").read_text(encoding="utf-8")
    a = Path("src/admin.py").read_text(encoding="utf-8")
    assert "autoaprendizaje.guardar_ham_si_procede(" in h
    assert "autoaprendizaje.aprender_spam_de_ban(" in h
    assert "autoaprendizaje.proponer_reglas(" in h and "autoaprendizaje.proponer_reglas(" in a
    assert "olvidar_ham_automatico(" in f and "olvidar_spam_automatico(" in f
