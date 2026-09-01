"""El aviso de «algo raro de alguien de confianza» no puede repetirse en bucle.

Medido el 1-sep-2026: el admin escribió «@spam» cuatro veces seguidas probando el
bot y recibió **cuatro avisos idénticos en 66 segundos** (mensajes 60501, 60503,
60505 y 60507). Cada `@algo` que no resuelve a nadie del grupo cuenta como
mención externa, así que la regla saltaba en todos.

No era un fallo de duplicación —eran cuatro mensajes reales— sino de ruido: el
primero informa y los tres siguientes sobran. Y en este proyecto un aviso que se
acaba ignorando es peor que no tenerlo.

No se pierde información: los `gentle_warn` se siguen registrando TODOS en
`moderation_log`, que es donde se consultan.
"""
from pathlib import Path

import pytest

from src import handlers


def _bloque() -> str:
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def _send_trust_notice(")
    return fuente[i:fuente.index("\nasync def ", i + 10)]


def test_hay_freno_por_persona_regla_y_chat():
    bloque = _bloque()
    assert "_CLAVE_AVISO_TRUST" in bloque
    assert "msg.chat_id, user.id" in bloque, "la clave debe distinguir chat y persona"
    assert "sorted(rules)" in bloque, "y también la regla que saltó"


def test_media_hora_es_el_plazo():
    assert handlers._AVISO_TRUST_CADA_S == 30 * 60


def test_el_registro_no_se_toca():
    """El freno es solo del AVISO: la acción se sigue anotando siempre."""
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def _send_trust_notice(")
    # El log_action del gentle_warn vive fuera de esta función, en la ruta normal.
    assert "db.log_action" not in _bloque(), (
        "el aviso no debería registrar: si el freno se lo salta, se perdería el dato")
    assert i > 0


def test_el_recuerdo_no_crece_sin_fin():
    bloque = _bloque()
    assert "del cache[k]" in bloque, "sin purga, el diccionario solo crece"


@pytest.mark.asyncio
async def test_el_mismo_aviso_no_se_manda_dos_veces(monkeypatch):
    """Comportamiento: dos mensajes seguidos con la misma regla, un solo aviso."""
    from types import SimpleNamespace as NS

    enviados = []

    class _Bot:
        async def send_message(self, chat_id, text, **kw):
            enviados.append(text)
            return NS(message_id=1)

    class _DB:
        pass

    monkeypatch.setattr(handlers.notify_prefs, "effective", lambda *a, **k: True)
    ctx = NS(bot=_Bot(), bot_data={}, application=NS(job_queue=None))
    cfg = NS(admin_notify_chat_id=7, mode="active")
    user = NS(id=9274244, first_name="yo", username="YoQueSe", is_bot=False)

    def _msg(texto, mid):
        return NS(text=texto, caption=None, chat_id=-100, message_id=mid,
                  chat=NS(id=-100, title="Windows 11"))

    for mid, texto in ((60501, "@spam"), (60503, "@spam")):
        await handlers._send_trust_notice(
            ctx, _DB(), cfg, _msg(texto, mid), user,
            ["external_mention_or_link"], "Mención a 1 externo/s", "gentle_warn", 90)

    assert len(enviados) == 1, f"llegaron {len(enviados)} avisos por la misma regla"


@pytest.mark.asyncio
async def test_otra_regla_si_avisa(monkeypatch):
    """El freno es por regla: algo distinto merece su propio aviso."""
    from types import SimpleNamespace as NS

    enviados = []

    class _Bot:
        async def send_message(self, chat_id, text, **kw):
            enviados.append(text)
            return NS(message_id=1)

    monkeypatch.setattr(handlers.notify_prefs, "effective", lambda *a, **k: True)
    ctx = NS(bot=_Bot(), bot_data={}, application=NS(job_queue=None))
    cfg = NS(admin_notify_chat_id=7, mode="active")
    user = NS(id=1, first_name="yo", username="u", is_bot=False)
    msg = NS(text="x", caption=None, chat_id=-100, message_id=1,
             chat=NS(id=-100, title="W11"))

    await handlers._send_trust_notice(ctx, object(), cfg, msg, user,
                                      ["external_mention_or_link"], "r", "gentle_warn", 90)
    await handlers._send_trust_notice(ctx, object(), cfg, msg, user,
                                      ["commercial_ad"], "r", "gentle_warn", 90)
    assert len(enviados) == 2
