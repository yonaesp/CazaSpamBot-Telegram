"""Toda hora que ve una persona pasa por aquí.

El bot mezcla dos orígenes de fechas y cada uno viene en una zona distinta:

- **La base de datos y los logs** guardan `time.time()` y se formatean con
  `datetime.fromtimestamp()`, que usa la zona del proceso (aquí `Europe/Madrid`).
- **Telethon** (admin_log, fotos de perfil, fecha de creación de cuenta) devuelve
  datetimes **en UTC**, con `tzinfo` puesto.

Formatearlos a pelo con `.strftime()` mezcla las dos cosas en la misma pantalla:
`/quienfue` mostraba las horas del registro de administración **dos horas
atrasadas** respecto a `/recent`, que sale de la base. Nadie lo había notado
porque las dos parecen horas plausibles.

Costó tiempo de verdad el 2026-08-23, investigando por qué un usuario decía que
el bot le insistía: los logs decían 11:16 y el registro de Telegram 09:16, y
parecían eventos distintos cuando eran el mismo. De ahí este módulo.

Regla: **cualquier fecha que se le muestre a una persona se formatea con
`cuando()` o `dia()`**, vengan de donde vengan. Hay un meta-test que lo vigila.
"""
from __future__ import annotations

import datetime as _dt
import logging

log = logging.getLogger(__name__)


def _a_local(valor) -> _dt.datetime | None:
    """Normaliza a un datetime en la zona del bot. Acepta datetime o epoch."""
    if valor is None:
        return None
    try:
        if isinstance(valor, (int, float)):
            return _dt.datetime.fromtimestamp(float(valor))
        if isinstance(valor, _dt.datetime):
            # Con tzinfo (lo que da Telethon) se CONVIERTE; sin él ya es local.
            if valor.tzinfo is not None:
                return valor.astimezone()
            return valor
        if isinstance(valor, _dt.date):
            # Una fecha suelta no tiene hora ni zona que convertir (p. ej. la
            # creación estimada de una cuenta): se muestra tal cual.
            return _dt.datetime(valor.year, valor.month, valor.day)
    except (ValueError, OSError, OverflowError) as exc:
        log.debug("fecha ilegible %r: %s", valor, exc)
    return None


def cuando(valor, formato: str = "%d/%m %H:%M") -> str:
    """Fecha y hora para mostrar. `?` si no hay dato o no se puede leer."""
    d = _a_local(valor)
    return d.strftime(formato) if d else "?"


def dia(valor, formato: str = "%d/%m/%Y") -> str:
    """Solo la fecha, para cosas como la antigüedad de una cuenta."""
    return cuando(valor, formato)
