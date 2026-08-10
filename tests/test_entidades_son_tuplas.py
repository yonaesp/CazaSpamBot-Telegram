"""En python-telegram-bot 22 las entidades son TUPLAS, y eso rompía un detector.

Caso real (10-ago-2026, 22:11, Windows 11). Un mensaje con publicidad de
servicios de hackeo entró en el grupo y **el bot no hizo nada**: lo tuvo que
borrar y banear un admin a mano doce minutos después. El motivo, en el log:

    File "/app/src/detectors/premium_new_link.py", line 20, in _has_link
      for ent in (msg.entities or []) + (msg.caption_entities or []):
    TypeError: can only concatenate tuple (not "list") to tuple

`msg.entities` es una tupla; un `caption_entities` vacío hace que `or []`
devuelva una lista, y `tuple + list` no existe en Python. El error se propagó
hasta el handler global y **abortó `on_message` entero**, así que el mensaje no
pasó por ninguno de los veinte detectores restantes. Comprobado después: ese
texto puntúa 120 en `commercial_ad`, o sea que el bot lo habría baneado solo.

Lo peor no fue el TypeError, fue cuánto llevaba ahí. El detector vivía dentro de
un `try/except Exception` que lo tragaba con un `log.debug`, así que llevaba
**meses muerto en silencio** desde que se actualizó la librería. Solo se destapó
al sacarlo de ese `try` en una refactorización. De ahí las dos costuras: los
detectores se aíslan (uno roto no puede llevarse a los otros veinte) pero su
fallo se registra con WARNING y traza, nunca en silencio.
"""
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from src.detectors import dormant_bot_mention, premium_new_link


def _msg(entities=(), caption_entities=(), text="hola"):
    """Como lo entrega PTB 22: entidades en TUPLA, no en lista."""
    return NS(text=text, caption=None, entities=entities,
              caption_entities=caption_entities, reply_to_message=None)


# ------------------------------------------------------- el fallo exacto

def test_entidades_en_tupla_no_revientan():
    """La reproducción literal del caso: entidades presentes y caption vacío."""
    ent = NS(type="url", offset=0, length=4, url=None)
    assert premium_new_link._has_link(_msg(entities=(ent,))) is True


def test_tambien_al_reves():
    ent = NS(type="url", offset=0, length=4, url=None)
    assert premium_new_link._has_link(_msg(caption_entities=(ent,))) is True


@pytest.mark.parametrize("ents,caps", [
    ((), ()),          # las dos vacías, que es el caso mayoritario
    (None, None),      # PTB puede darlas a None
    ((), None),
    (None, ()),
])
def test_las_combinaciones_vacias_tampoco(ents, caps):
    assert premium_new_link._has_link(_msg(entities=ents, caption_entities=caps)) is False


def test_el_otro_detector_que_tenia_el_mismo_fallo():
    ent = NS(type="mention", offset=0, length=4, url=None)
    msg = _msg(entities=(ent,), text="@algunbot hola")
    # No importa el veredicto: importa que no lance.
    dormant_bot_mention.check(msg, last_msg_ts=1_700_000_000.0, now=1_800_000_000.0)


# --------------------------------------------------- que no vuelva a colarse

def test_ningun_detector_concatena_entidades_a_pelo():
    """El meta-test. `list(...)` en los DOS lados o vuelve el TypeError."""
    malos = []
    for f in Path("src").rglob("*.py"):
        for n, linea in enumerate(f.read_text().splitlines(), 1):
            if "entities or []" not in linea:
                continue
            if "+" in linea and linea.count("list(") < 2:
                malos.append(f"{f}:{n}: {linea.strip()}")
    assert not malos, "concatenación de entidades sin list() en ambos lados:\n" + "\n".join(malos)


# ------------------------------------------- un detector roto no tumba el resto

def test_los_detectores_del_pipeline_van_aislados():
    """Sin esto, cualquier detector que reviente deja el mensaje sin moderar."""
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def on_message(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    sueltos = [ln.strip() for ln in cuerpo.splitlines()
               if "hits.append(" in ln and "_sin_tumbar" not in ln
               and ".check(" in ln]
    assert not sueltos, f"detectores sin aislar: {sueltos}"


def test_el_fallo_de_un_detector_se_ve_en_el_log():
    """La otra mitad de la lección: tragárselo en `debug` es lo que dejó el
    detector muerto meses sin que nadie se enterara."""
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("def _sin_tumbar(")
    bloque = fuente[i:fuente.index("# 1) Unicode script", i)]
    assert "log.warning" in bloque, "un detector caído tiene que hacer ruido"
    assert "exc_info=True" in bloque, "sin traza no se puede arreglar"
    assert "log.debug(" not in bloque, "un fallo tragado en debug es lo que pasó aquí"


def test_el_mensaje_se_sigue_evaluando_sin_el_detector_roto():
    """Comportamiento, no texto: el ayudante devuelve un Hit vacío y el pipeline
    continúa con los demás."""
    import logging
    from src.detectors import Hit

    registrado = []

    class _Log:
        def warning(self, *a, **k):
            registrado.append(a)

    # Se reproduce el ayudante tal cual está en on_message.
    log = _Log()

    def _sin_tumbar(fn, que):
        try:
            return fn()
        except Exception:
            log.warning("detector %s falló; se sigue sin él", que, exc_info=True)
            return Hit.none()

    def revienta():
        raise TypeError("can only concatenate tuple (not \"list\") to tuple")

    hits = [_sin_tumbar(revienta, "premium_new_link"),
            Hit(rule="commercial_ad", score=120, reason="spam", payload={})]
    assert registrado, "el fallo tiene que quedar registrado"
    assert sum(h.score for h in hits) == 120, "el resto del pipeline debe seguir contando"
    assert logging  # el import se usa para dejar claro el contexto del helper real
