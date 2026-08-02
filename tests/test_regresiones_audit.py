"""Regresiones de la auditoría del 2 de agosto. Un test por fallo real.

Ninguno de estos lo detectaba la batería anterior, y varios los introduje yo en
refactors de los días previos. El más grave dejaba muteado para siempre a un
usuario legítimo en OTRO grupo.
"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db import DB


# ---------------------------------------------------------------- 1) CRÍTICO

def test_la_limpieza_de_bienvenidas_tiene_guarda_de_accion():
    """`_apply_action` corre con CUALQUIER decisión, también `noop`. Sin guarda,
    la limpieza borraba la fila `pending_verifications` del usuario en TODOS los
    chats, así que un recién llegado que saluda a los 10 segundos (30 puntos =
    noop, o sea el bot NO sanciona) perdía su verificación pendiente en otro
    grupo y se quedaba muteado para siempre: al pulsar SOY HUMANO el bot no
    encontraba la fila y no le quitaba el mute.
    """
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("limpiar_bienvenidas(context, db, user_id)")
    contexto = fuente[max(0, i - 400):i]
    assert 'decision.action in ("ban", "kick")' in contexto, (
        "la limpieza se ejecuta sin comprobar la acción: borrará verificaciones "
        "pendientes de usuarios a los que el bot ha decidido NO sancionar"
    )
    assert "not cfg.shadow" in contexto, (
        "la limpieza se ejecuta en modo shadow, que no debe tocar nada"
    )


@pytest.mark.asyncio
async def test_limpiar_bienvenidas_borra_pendientes_de_todos_los_chats(tmp_path):
    """Fija POR QUÉ hace falta la guarda: la función es agresiva a propósito
    (un ban es federado), y por eso no puede llamarse a la ligera."""
    from src import verification
    db = DB(str(tmp_path / "t.db"))
    for cid in (-100111, -100222):
        db.upsert_bot_chat(cid, "G", "supergroup", True, True, True)
        db.ensure_chat_settings(cid)
    db.add_pending_verification(chat_id=-100222, user_id=777,
                                welcome_msg_id=9001, is_suspicious=False)
    ctx = MagicMock()
    ctx.bot.delete_message = AsyncMock()
    await verification.limpiar_bienvenidas(ctx, db, 777)
    assert db.get_pending(-100222, 777) is None


# ---------------------------------------------------------------- 2) defaults

def test_los_defaults_del_detector_tambien_son_parejas():
    """El Dockerfile NO copia `config/`: aquí llega por bind-mount, pero un
    `docker run` de la imagen pelada se queda con estos defaults. Cuando eran
    palabras sueltas, baneaban «Windows Insider Program» y «Heat Pump UK»."""
    import re
    from src.detectors.story_share import _FUENTE_DEFAULTS
    rx = re.compile("|".join(_FUENTE_DEFAULTS), re.IGNORECASE)
    legitimos = ["Windows Insider Program", "Heat Pump UK", "Signal Messenger",
                 "Rich Text Editor", "Casino Royale", "Whale Watching Tarifa",
                 "Business Insider", "Zürich Nachrichten", "Pumpkin Recipes"]
    fallos = [n for n in legitimos if rx.search(n)]
    assert not fallos, f"los defaults banearían canales legítimos: {fallos}"

    spam = ["Crypto Signals VIP", "Insider Group Signal", "Free Airdrop Daily",
            "Online Casino Bonus", "OnlyFans Leaks"]
    escapan = [n for n in spam if not rx.search(n)]
    assert not escapan, f"los defaults no cazan spam evidente: {escapan}"


# ---------------------------------------------------------------- 3) timeout

@pytest.mark.asyncio
async def test_leer_una_historia_tiene_tope_de_tiempo_total(monkeypatch):
    """El tope era por llamada y se encadenaban hasta tres: medido, 10,3 s con el
    bot congelado, porque PTB procesa los updates de uno en uno."""
    from src import story_reader

    async def _eterno(*a, **k):
        await asyncio.sleep(30)

    monkeypatch.setattr(story_reader, "_leer", _eterno)
    monkeypatch.setattr(story_reader, "_TIMEOUT_TOTAL_S", 0.2)
    import time
    t0 = time.monotonic()
    res = await story_reader.leer_caption(MagicMock(), MagicMock())
    tardo = time.monotonic() - t0
    assert res is None
    assert tardo < 1.0, f"no cortó a tiempo: {tardo:.1f}s"


# ---------------------------------------------------------------- 4) HTML

def test_el_ack_escapa_el_nombre_del_spammer():
    """Los nombres decorativos son marca de la casa del spam. Con `Kira</b>` el
    HTML quedaba desbalanceado, Telegram rechazaba el mensaje ENTERO y el admin
    se quedaba sin acuse: justo el fallo que ese código venía a cerrar."""
    fuente = Path("src/admin.py").read_text()
    assert "name=author.first_name," not in fuente, (
        "el nombre del spammer se interpola en HTML sin escapar"
    )


# ---------------------------------------------------------------- 5) URLs

def test_el_dominio_no_se_come_caracteres():
    """`lstrip("www.")` recibe un CONJUNTO de caracteres: convertía `wa.me` en
    `a.me`. Inofensivo con la lista actual, pero el día que se añada wa.me (vector
    habitual) el detector no casaría y nadie vería ningún error."""
    # Mirando el CÓDIGO, no los comentarios: el propio comentario que explica el
    # fallo contiene la cadena `lstrip("www.")`.
    codigo = "\n".join(linea.split("#")[0] for linea in
                       Path("src/detectors/url_blocklist.py").read_text().splitlines())
    assert 'lstrip("www.")' not in codigo, "sigue usando lstrip para quitar el prefijo"
    for host, esperado in (("wa.me", "wa.me"), ("www.wa.me", "wa.me"),
                           ("whatsapp.com", "whatsapp.com"), ("w.wiki", "w.wiki")):
        assert host.removeprefix("www.") == esperado


# ---------------------------------------------------------------- 6) barrido

def test_el_barrido_solo_olvida_si_el_mensaje_ya_no_esta():
    """Antes soltaba el registro pasara lo que pasara, así que un fallo transitorio
    (flood control, corte de red) dejaba la bienvenida del baneado en el grupo para
    siempre. Solo había UN reintento, no un reintento persistente."""
    fuente = Path("src/verification.py").read_text()
    i = fuente.index("bienvenidas_de_baneados()")
    bloque = fuente[i:i + 900]
    assert "soltar" in bloque, "el barrido no distingue el fallo transitorio del definitivo"
