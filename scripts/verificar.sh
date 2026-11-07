#!/bin/bash
# Todas las comprobaciones del código, de la más rápida a la más lenta (L56). Sale ≠ 0 si algo falla.
#   scripts/verificar.sh            todo: ruff, compilación, suite y simulador
#   scripts/verificar.sh --rapido   sin la suite (para el hook de cada edición)
# Lo llaman el pre-commit (.githooks) y el hook Stop de Claude Code; a mano, igual.
set -u
cd "$(dirname "$0")/.." || exit 2
PY=.venv/bin/python
fallo=0
paso() { printf '· %s… ' "$1"; }
ok() { echo "ok"; }
mal() { echo "FALLA"; fallo=1; }

paso "ruff (src, tests)"
if out=$(.venv/bin/ruff check src/ tests/ 2>&1); then ok; else mal; echo "$out" | tail -40; fi

paso "compilación"
if out=$($PY -m compileall -q src/ 2>&1); then ok; else mal; echo "$out" | tail -20; fi

paso "JSON de idiomas"
if out=$($PY -c 'import json,glob
for f in glob.glob("src/locales/*.json"): json.load(open(f, encoding="utf-8"))' 2>&1); then ok; else mal; echo "$out" | tail -5; fi

if [ "${1:-}" != "--rapido" ]; then
    paso "suite"
    log=$(mktemp)
    if $PY -m pytest tests/ -q -p no:warnings -x > "$log" 2>&1; then ok; tail -1 "$log"
    else mal; grep -E "^(FAILED|ERROR)|^E  " "$log" | head -40; tail -3 "$log"; fi
    rm -f "$log"
    paso "simulador (scripts/simular.py --vacia)"
    if out=$($PY scripts/simular.py --vacia 2>&1); then ok; else mal; echo "$out" | tail -20; fi
fi
exit $fallo
