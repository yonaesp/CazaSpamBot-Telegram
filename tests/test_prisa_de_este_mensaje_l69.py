"""La prisa se mide en ESTE mensaje, no en el primero (L69).

Caso real (27-nov-2026, Windows 11): una cuenta entró el 12-oct, escribió a los 21 s
y otra vez enseguida, y 46 días después mandó una foto (su tercer mensaje). La foto
cargó «escribió a los 21 s de entrar» (`jfm_fast`) porque la prisa se calculaba
siempre con el primer mensaje, y entraba en los tres primeros. Era spam y cayó, pero
una persona normal que escribe pronto y más tarde manda una foto habría caído igual.
"""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path
from types import SimpleNamespace as NS

from src import handlers
from src.detectors import jfm_delta as det

ENTRADA = dt.datetime(2026, 10, 12, 12, 5, 30, tzinfo=dt.timezone.utc)


def _fila(join=ENTRADA):
    return {"join_ts": join.timestamp() if join else None}


def _msg(segundos: float):
    return NS(date=ENTRADA + dt.timedelta(seconds=segundos))


def test_la_foto_46_dias_despues_no_es_prisa():
    delta = handlers._retraso_desde_la_entrada(_fila(), _msg(46 * 86400))
    assert not det.check(is_first_msg=True, delta_seconds=delta, cron=False)


def test_el_primer_mensaje_a_los_21_s_sigue_siendo_prisa():
    delta = handlers._retraso_desde_la_entrada(_fila(), _msg(21))
    assert det.check(is_first_msg=True, delta_seconds=delta).rule == "jfm_fast"


def test_el_segundo_mensaje_tambien_rapido_cuenta():
    """Un bot que suelta tres mensajes en 10 s: los tres llegan con prisa de verdad."""
    delta = handlers._retraso_desde_la_entrada(_fila(), _msg(3))
    assert det.check(is_first_msg=True, delta_seconds=delta, cron=False).rule == "jfm_too_fast"


def test_las_24_h_justas_solo_en_el_primero():
    assert det.check(is_first_msg=True, delta_seconds=24 * 3600).rule == "jfm_cron"
    assert not det.check(is_first_msg=True, delta_seconds=24 * 3600, cron=False)


def test_sin_entrada_vista_no_hay_prisa():
    assert handlers._retraso_desde_la_entrada(_fila(join=None), _msg(5)) is None
    assert handlers._retraso_desde_la_entrada(None, _msg(5)) is None


def test_on_message_no_vuelve_a_usar_la_hora_del_primer_mensaje():
    """La prisa sale de `_retraso_desde_la_entrada`; `first_msg_ts` no entra en la cuenta."""
    fuente = Path("src/handlers.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and getattr(nodo.func, "attr", None) == "check" \
                and getattr(getattr(nodo.func, "value", None), "id", None) == "jfm_det":
            kws = {k.arg for k in nodo.keywords}
            assert "cron" in kws
    assert '"first_msg_ts"]) - float(seen_row["join_ts"]' not in fuente
