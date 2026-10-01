"""Mejoras de la revisión del 1-oct-2026, cada una con su medida real."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from telegram.error import BadRequest, NetworkError

from src import handlers


def _ctx(exc):
    async def _gcm(**kw):
        raise exc
    return SimpleNamespace(bot=SimpleNamespace(get_chat_member=_gcm), bot_data={})


def test_quien_no_es_miembro_no_es_admin():
    """Caso real: un spammer fichado en lols.bot que ya se había ido. La guarda
    asumía «admin» ante «Member not found» y lo frenó 37 veces en una semana."""
    for msg in ("Member not found", "User not found", "USER_NOT_PARTICIPANT",
                "Participant_id_invalid"):
        assert asyncio.run(handlers._is_admin_of_chat(_ctx(BadRequest(msg)), -100, 1)) is False, msg


def test_un_fallo_dudoso_sigue_cayendo_del_lado_seguro():
    """Red caída o Telegram con problemas: no se sabe, así que se asume admin."""
    assert asyncio.run(handlers._is_admin_of_chat(_ctx(NetworkError("timeout")), -100, 1)) is True
    assert asyncio.run(handlers._is_admin_of_chat(_ctx(BadRequest("Chat not found")), -100, 1)) is True


def test_el_motivo_libre_de_ban_y_unban_se_escapa():
    fuente = Path("src/admin.py").read_text(encoding="utf-8")
    assert 't("admin.quip_reason", reason=html.escape(reason))' in fuente
    assert 't("admin.quip_reason", reason=html.escape(reason_raw))' in fuente
    assert 't("admin.quip_reason", reason=reason' not in fuente


def test_los_comandos_no_esperan_a_telethon_sin_tope():
    """Dentro de un comando, una espera de Telethon para el bot entero."""
    assert "asyncio.wait_for(client.get_entity(" in Path("src/admin.py").read_text(encoding="utf-8")
    q = Path("src/quienfue_cmd.py").read_text(encoding="utf-8")
    assert "asyncio.wait_for(client.get_input_entity(" in q


# --- aprendizaje cacheado: mismo resultado, sin recalcular las muestras --------

def test_el_coseno_cacheado_da_lo_mismo_que_el_original():
    """Medido el 1-oct-2026: 352 mensajes reales, 0 resultados distintos, y de 38 ms
    a 3 ms por mensaje con 200 + 200 muestras."""
    from src import learning as L
    textos = ["hola buenas, alguien sabe por qué no arranca windows tras la actualización",
              "gana 500€ al día desde casa escríbeme por privado ahora",
              "vendo cuentas verificadas binance baratas", "ok"]
    for a in textos:
        for b in textos:
            ga, gb = L._char_ngrams(a), L._char_ngrams(b)
            _, na = L._vector_muestra(a)
            _, nb = L._vector_muestra(b)
            assert abs(L._cosine(ga, gb) - L._cosine_con_norma(ga, na, gb, nb)) < 1e-12


def test_el_modelo_bayes_se_reutiliza_mientras_no_cambian_las_muestras():
    from src import learning as L
    spam = tuple(f"oferta gana dinero rápido número {i}" for i in range(12))
    ham = tuple(f"no me arranca el portátil después de actualizar {i}" for i in range(12))
    L._modelo_bayes.cache_clear()
    L.naive_bayes_spam_prob("gana dinero", list(spam), list(ham))
    L.naive_bayes_spam_prob("otra cosa distinta", list(spam), list(ham))
    assert L._modelo_bayes.cache_info().hits >= 1
