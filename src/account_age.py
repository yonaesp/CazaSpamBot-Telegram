"""Estimar cuándo se creó una cuenta de Telegram a partir de su `user_id`.

Telegram **no publica** la fecha de alta. Pero los `user_id` se reparten de forma
casi secuencial en el tiempo, así que interpolando entre puntos conocidos se saca
una aproximación útil para moderar: distinguir «cuenta de hace una semana» de
«cuenta de hace ocho años», que es la pregunta que importa.

Es una ESTIMACIÓN y se presenta como tal. Nunca como un dato duro:

- La precisión es de semanas o meses, no de días.
- Telegram ha cambiado el ritmo de asignación varias veces (los tramos no son
  lineales entre sí, por eso hay tantos anclajes).
- Por encima del último anclaje se extrapola, así que las cuentas muy nuevas son
  las menos precisas justo cuando más importa. Ahí se devuelve el margen.

Lo que el bot ya tenía (`user_signals.account_age_days`) NO es esto: se deduce de
la foto de perfil más antigua, así que solo da una cota inferior y falla del todo
si el usuario no tiene foto o la cambió. Las dos señales se complementan.
"""
from __future__ import annotations

import datetime as _dt

# Anclajes (user_id, fecha). Son puntos públicos y conocidos del reparto de ids.
# Ordenados; la interpolación es lineal por tramos.
_ANCLAS: list[tuple[int, str]] = [
    (1_000_000, "2013-08-01"),
    (10_000_000, "2014-06-01"),
    (50_000_000, "2015-06-01"),
    (100_000_000, "2016-01-01"),
    (150_000_000, "2016-09-01"),
    (200_000_000, "2017-04-01"),
    (300_000_000, "2018-02-01"),
    (400_000_000, "2018-09-01"),
    (500_000_000, "2019-04-01"),
    (700_000_000, "2020-01-01"),
    (900_000_000, "2020-09-01"),
    (1_000_000_000, "2021-01-01"),
    (1_300_000_000, "2021-08-01"),
    (1_700_000_000, "2022-02-01"),
    (2_000_000_000, "2022-09-01"),
    (5_000_000_000, "2023-11-01"),
    (6_000_000_000, "2024-04-01"),
    (7_000_000_000, "2024-11-01"),
    (7_500_000_000, "2025-04-01"),
    (8_000_000_000, "2025-09-01"),
    (8_500_000_000, "2026-02-01"),
    # Anclaje VERIFICADO: cuenta creada el 23-may-2026, id conocido. Los puntos
    # medidos valen más que los aproximados, sobre todo en el tramo reciente,
    # que es donde caen las cuentas de spam.
    (8_714_716_537, "2026-05-23"),
    (9_000_000_000, "2026-07-01"),
]


def _a_fecha(txt: str) -> _dt.date:
    return _dt.date.fromisoformat(txt)


def estimar(user_id: int) -> tuple[_dt.date, str] | None:
    """(fecha estimada, precisión) o None si el id no es utilizable.

    `precisión` es una etiqueta corta: `"alta"` dentro del rango de anclajes,
    `"baja"` si hay que extrapolar por arriba (cuentas muy recientes) o por abajo.
    """
    if not isinstance(user_id, int) or user_id <= 0:
        return None
    # Los bots y los ids de canal no son cuentas de persona: no procede estimar.
    if user_id > 100_000_000_000:
        return None

    if user_id <= _ANCLAS[0][0]:
        return _a_fecha(_ANCLAS[0][1]), "baja"
    if user_id >= _ANCLAS[-1][0]:
        # Extrapolación con el ritmo del último tramo. Es lo menos fiable, y
        # justo donde caen las cuentas recién creadas, así que se marca.
        (id_a, fecha_a), (id_b, fecha_b) = _ANCLAS[-2], _ANCLAS[-1]
        dias = (_a_fecha(fecha_b) - _a_fecha(fecha_a)).days
        por_id = dias / max(1, id_b - id_a)
        extra = int((user_id - id_b) * por_id)
        estimada = _a_fecha(fecha_b) + _dt.timedelta(days=extra)
        # Nunca en el futuro: una cuenta no puede haberse creado mañana.
        hoy = _dt.date.today()
        return (min(estimada, hoy), "baja")

    for (id_a, fecha_a), (id_b, fecha_b) in zip(_ANCLAS, _ANCLAS[1:]):
        if id_a <= user_id <= id_b:
            proporcion = (user_id - id_a) / max(1, id_b - id_a)
            dias = (_a_fecha(fecha_b) - _a_fecha(fecha_a)).days
            return _a_fecha(fecha_a) + _dt.timedelta(days=int(dias * proporcion)), "alta"
    return None
