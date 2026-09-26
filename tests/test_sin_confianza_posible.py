"""Sin historial + reenvío de un bot o formato ilegible = el trust no ablanda nada.

Decisión del admin (26-sep-2026), tras una cuenta dentro desde junio, sin un solo
mensaje en 3 meses, cuyo primer mensaje fue un reenvío de un bot con publicidad
porno y un botón a una web (la cuenta secundaria lo recibe como
`MessageMediaUnsupported`). El trust por antigüedad lo convirtió en tres preguntas.
"""
from __future__ import annotations

import ast
from pathlib import Path

from src import handlers
from src.detectors import Hit


class _DB:
    def __init__(self, msgs):
        self.msgs = msgs

    def get_seen(self, chat_id, user_id):
        return None if self.msgs is None else {"msg_count": self.msgs}


def _fwd(origen):
    return Hit(rule="forward_first_msg", score=95, reason="x",
               payload={"origin_type": origen})


def _motivo(msgs, real, opaco=False):
    return handlers._sin_confianza_posible(_DB(msgs), -100, 1, real, opaco)


def test_el_caso_real_primer_mensaje_reenviado_de_un_bot():
    assert _motivo(1, [_fwd("bot")])


def test_formato_ilegible_sin_historial():
    assert _motivo(1, [_fwd("user")], opaco=True)


def test_quien_ya_ha_escrito_conserva_su_trust():
    """La regla es para quien NUNCA ha escrito; con historial manda el trust."""
    assert _motivo(2, [_fwd("bot")]) == ""
    assert _motivo(30, [_fwd("bot")], opaco=True) == ""


def test_otros_reenvios_no_entran():
    """Lo pedido es «reenvío de un bot»: el de un usuario sigue su curso."""
    assert _motivo(1, [_fwd("user")]) == ""


def test_sin_fila_no_se_afirma_nada():
    assert _motivo(None, [_fwd("bot")]) == ""


def test_se_aplica_en_los_dos_sitios_donde_el_trust_ablanda():
    """La graduación suave y el bloque de trust: si falta en uno, por ahí se cuela."""
    fuente = Path("src/handlers.py").read_text(encoding="utf-8")
    assert "only_borderline and not _motivo_sin_confianza" in fuente
    assert "not has_hard_rule and not _motivo_sin_confianza" in fuente
    # y se calcula ANTES de usarse
    arbol = ast.parse(fuente)
    asign = [n.lineno for n in ast.walk(arbol) if isinstance(n, ast.Assign)
             and any(getattr(t, "id", "") == "_motivo_sin_confianza" for t in n.targets)]
    usos = [n.lineno for n in ast.walk(arbol) if isinstance(n, ast.Name)
            and n.id == "_motivo_sin_confianza" and isinstance(n.ctx, ast.Load)]
    assert asign and min(asign) < min(usos)
