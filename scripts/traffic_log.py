#!/usr/bin/env python3
"""Registra en local el tráfico del repo en GitHub (visitas y clones).

GitHub solo guarda los últimos 14 días de tráfico y lo tira. Este script lee
esa ventana y la va ACUMULANDO en un fichero local, de modo que ejecutándolo de
vez en cuando (un par de veces al mes basta, siempre dentro de esos 14 días) se
construye un histórico que GitHub no conserva.

Uso:
    python -m scripts.traffic_log          # lee de GitHub, fusiona y muestra resumen
    python -m scripts.traffic_log --show   # solo muestra lo ya guardado, sin llamar a la API

Requiere `gh` autenticado con permiso sobre el repo (scope `repo`):
    gh auth status

El histórico se guarda en traffic/history.json (gitignored: es dato de tu
despliegue, no del código). Es SEGURO ejecutarlo dos veces el mismo día: se
fusiona por fecha, nunca duplica ni infla.
"""
from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# traffic/ y no data/ a propósito: data/ suele pertenecer al contenedor Docker
# (root) y este script corre como tu usuario. traffic/ está gitignored igual.
_HIST = _ROOT / "traffic" / "history.json"


def _repo_slug() -> str:
    """owner/repo a partir del remote `origin` (soporta https y ssh)."""
    url = subprocess.run(
        ["git", "-C", str(_ROOT), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    slug = url.rsplit("github.com", 1)[-1].lstrip(":/")
    return slug[:-4] if slug.endswith(".git") else slug


def _gh_traffic(slug: str, kind: str) -> list[dict]:
    """Serie diaria de GitHub. `kind` es 'views' o 'clones'. La clave con la
    lista se llama igual que el endpoint ('views' / 'clones')."""
    out = subprocess.run(
        ["gh", "api", f"repos/{slug}/traffic/{kind}"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise SystemExit(
            f"gh api falló para {kind}: {out.stderr.strip() or out.stdout.strip()}\n"
            "Comprueba `gh auth status` y que tienes permiso sobre el repo."
        )
    return json.loads(out.stdout).get(kind, [])


def _load() -> dict:
    try:
        return json.loads(_HIST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Sin histórico previo o fichero corrupto: se empieza de cero. No se
        # aborta por esto, el objetivo es no perder las lecturas siguientes.
        return {"views": {}, "clones": {}}


def _merge(hist: dict, serie: list[dict], kind: str) -> int:
    """Vuelca la serie de GitHub en el histórico, indexada por día.

    Se sobrescribe por fecha A PROPÓSITO: un día ya cerrado devuelve siempre el
    mismo valor, y el día en curso devuelve el valor actualizado, así que la
    lectura más reciente de cada fecha es la buena. Por eso ejecutarlo de más
    nunca infla las cifras. Devuelve cuántas fechas nuevas se añadieron."""
    tabla = hist.setdefault(kind, {})
    nuevas = 0
    for punto in serie:
        dia = punto["timestamp"][:10]
        if dia not in tabla:
            nuevas += 1
        tabla[dia] = {"count": punto.get("count", 0), "uniques": punto.get("uniques", 0)}
    return nuevas


def _resumen(hist: dict) -> None:
    for kind, etiqueta in (("views", "VISITAS"), ("clones", "CLONES")):
        tabla = hist.get(kind, {})
        total = sum(d["count"] for d in tabla.values())
        dias = len(tabla)
        print(f"\n  {etiqueta} — {total} en total sobre {dias} días registrados")
        for dia in sorted(tabla)[-14:]:
            d = tabla[dia]
            barra = "#" * min(d["count"], 40)
            print(f"    {dia}  {d['count']:4}  ({d['uniques']:2} únicos)  {barra}")
    rango = sorted(set(hist.get("views", {})) | set(hist.get("clones", {})))
    if rango:
        print(f"\n  Histórico local: {rango[0]} → {rango[-1]}  ({_HIST})")


def main() -> None:
    hist = _load()
    if "--show" in sys.argv:
        if not hist.get("views") and not hist.get("clones"):
            print("  Aún no hay histórico. Ejecuta sin --show para registrar la primera lectura.")
            return
        _resumen(hist)
        return

    slug = _repo_slug()
    print(f"  Leyendo tráfico de {slug} (últimos 14 días que expone GitHub)...")
    nv = _merge(hist, _gh_traffic(slug, "views"), "views")
    nc = _merge(hist, _gh_traffic(slug, "clones"), "clones")
    hist["last_run"] = _dt.datetime.now().astimezone().isoformat(timespec="seconds")

    _HIST.parent.mkdir(parents=True, exist_ok=True)
    _HIST.write_text(json.dumps(hist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  Fusionado: {nv} días nuevos de visitas, {nc} de clones.")
    _resumen(hist)


if __name__ == "__main__":
    main()
