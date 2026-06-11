#!/bin/bash
# CazaSpamBot - Control script. Patrón clickdriver-monitor con paleta Catppuccin Mocha.

set -e

# Catppuccin Mocha
ROSEWATER='\033[38;5;224m'
PINK='\033[38;5;218m'
MAUVE='\033[38;5;183m'
RED='\033[38;5;210m'
PEACH='\033[38;5;216m'
YELLOW='\033[38;5;223m'
GREEN='\033[38;5;151m'
TEAL='\033[38;5;115m'
SKY='\033[38;5;152m'
BLUE='\033[38;5;111m'
LAVENDER='\033[38;5;147m'
NC='\033[0m'
BOLD='\033[1m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONTAINER="cazaspam-bot"
DB_HOST="$SCRIPT_DIR/data/antispam.db"
DB_CTN="/app/data/antispam.db"

container_exists() { docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; }
container_running() { docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; }

run_sql() {
    local query="$1"; local opts="$2"
    if command -v sqlite3 &>/dev/null && [ -f "$DB_HOST" ]; then
        if [ -n "$opts" ]; then sqlite3 $opts "$DB_HOST" "$query"
        else sqlite3 "$DB_HOST" "$query"; fi
    elif container_running; then
        if [ -n "$opts" ]; then docker exec "$CONTAINER" sqlite3 $opts "$DB_CTN" "$query"
        else docker exec "$CONTAINER" sqlite3 "$DB_CTN" "$query"; fi
    else
        echo "sqlite no disponible"; return 1
    fi
}

show_help() {
    echo -e "${BOLD}${MAUVE}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${MAUVE}║       CazaSpamBot - Panel de control             ║${NC}"
    echo -e "${BOLD}${MAUVE}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BOLD}Uso:${NC} ./ctl.sh [comando]"
    echo ""
    echo -e "${BOLD}${GREEN}Lifecycle:${NC}"
    echo -e "  ${YELLOW}up${NC}            Construye e inicia el contenedor"
    echo -e "  ${YELLOW}down${NC}          Para y elimina el contenedor"
    echo -e "  ${YELLOW}restart${NC}       Reinicia"
    echo -e "  ${YELLOW}rebuild${NC}       Reconstruye imagen y reinicia"
    echo -e "  ${YELLOW}status${NC}        Estado del bot + DB"
    echo ""
    echo -e "${BOLD}${GREEN}Observabilidad:${NC}"
    echo -e "  ${YELLOW}logs [N]${NC}      Últimas N líneas (default 50)"
    echo -e "  ${YELLOW}follow${NC}        Logs en tiempo real"
    echo -e "  ${YELLOW}stats${NC}         Métricas (chats, users, bans, acciones 24h)"
    echo -e "  ${YELLOW}recent [N]${NC}    Últimas N acciones de moderación"
    echo -e "  ${YELLOW}chats${NC}         Lista chats donde el bot está activo"
    echo -e "  ${YELLOW}bans${NC}          Lista usuarios baneados (federados)"
    echo ""
    echo -e "${BOLD}${GREEN}Modo / desarrollo:${NC}"
    echo -e "  ${YELLOW}shadow${NC}        Pone MODE=shadow en .env y reinicia"
    echo -e "  ${YELLOW}active${NC}        Pone MODE=active (¡acciones reales!) y reinicia"
    echo -e "  ${YELLOW}test${NC}          Ejecuta pytest dentro del contenedor"
    echo ""
    echo -e "${BOLD}${GREEN}Análisis avanzado (Telethon):${NC}"
    echo -e "  ${YELLOW}analyze${NC}       Reporta miembros sospechosos por chat"
    echo -e "  ${YELLOW}analyze-ban${NC}   Reporta + banea auto los CAS match (federado)"
    echo -e "  ${YELLOW}analyze-deep${NC}  Iteración agresiva (lento pero más exhaustivo)"
    echo ""
}

cmd_up() {
    echo -e "${BLUE}Construyendo e iniciando...${NC}"
    docker compose up -d --build
    echo -e "${GREEN}OK.${NC} ./ctl.sh status"
}

cmd_down() {
    echo -e "${PEACH}Deteniendo...${NC}"
    docker compose down
}

cmd_restart() {
    echo -e "${PEACH}Reiniciando...${NC}"
    docker compose restart
}

cmd_rebuild() {
    echo -e "${BLUE}Reconstruyendo imagen...${NC}"
    docker compose build --no-cache
    docker compose up -d
}

cmd_status() {
    echo -e "${BOLD}${MAUVE}=== Estado ===${NC}\n"
    if ! container_exists; then
        echo -e "${RED}Contenedor no existe. ./ctl.sh up${NC}"; return 1
    fi
    if container_running; then
        echo -e "Estado: ${GREEN}${BOLD}ACTIVO${NC}"
        echo -e "Uptime: $(docker ps --format '{{.Status}}' -f name=${CONTAINER})"
    else
        echo -e "Estado: ${YELLOW}${BOLD}PARADO${NC}"
    fi

    if [ -f .env ]; then
        MODE=$(grep -E '^MODE=' .env | head -1 | cut -d= -f2)
        echo -e "Modo: ${BOLD}${MODE}${NC}"
    fi

    if [ -f "$DB_HOST" ] || container_running; then
        echo ""
        CHATS=$(run_sql "SELECT COUNT(*) FROM bot_chats WHERE am_admin=1;" 2>/dev/null || echo "0")
        USERS=$(run_sql "SELECT COUNT(*) FROM seen_users;" 2>/dev/null || echo "0")
        BANS=$(run_sql "SELECT COUNT(*) FROM banned_users WHERE revoked_at IS NULL;" 2>/dev/null || echo "0")
        ACTS=$(run_sql "SELECT COUNT(*) FROM moderation_log WHERE ts >= strftime('%s','now')-86400;" 2>/dev/null || echo "0")
        echo -e "Chats activos: ${BOLD}${CHATS}${NC}"
        echo -e "Usuarios vistos: ${BOLD}${USERS}${NC}"
        echo -e "Banneados: ${BOLD}${RED}${BANS}${NC}"
        echo -e "Acciones 24h: ${BOLD}${ACTS}${NC}"
    fi
    echo ""
}

cmd_logs() {
    local N=${1:-50}
    container_exists || { echo -e "${RED}No existe${NC}"; return 1; }
    docker logs --tail "$N" "$CONTAINER" 2>&1
}

cmd_follow() {
    container_running || { echo -e "${RED}No está corriendo${NC}"; return 1; }
    docker logs -f "$CONTAINER" 2>&1
}

cmd_stats() {
    echo -e "${BOLD}${MAUVE}=== Stats ===${NC}\n"
    run_sql "
        SELECT 'Chats activos: ' || (SELECT COUNT(*) FROM bot_chats WHERE am_admin=1);
        SELECT 'Usuarios vistos: ' || (SELECT COUNT(*) FROM seen_users);
        SELECT 'Banneados: ' || (SELECT COUNT(*) FROM banned_users WHERE revoked_at IS NULL);
        SELECT 'Acciones totales: ' || (SELECT COUNT(*) FROM moderation_log);
        SELECT 'Acciones 24h: ' || (SELECT COUNT(*) FROM moderation_log WHERE ts >= strftime('%s','now')-86400);
        SELECT 'Reacciones registradas: ' || (SELECT COUNT(*) FROM reaction_events);
    "
    echo ""
    echo -e "${BOLD}Por regla (top 5):${NC}"
    run_sql "SELECT rule || ' (' || COUNT(*) || ')' FROM moderation_log GROUP BY rule ORDER BY COUNT(*) DESC LIMIT 5;"
}

cmd_recent() {
    local N=${1:-10}
    echo -e "${BOLD}${MAUVE}=== Últimas $N acciones ===${NC}\n"
    run_sql "
      SELECT strftime('%m-%d %H:%M', ts, 'unixepoch', 'localtime')
             || ' | ' || action || ' | user=' || COALESCE(user_id,'?')
             || ' | rule=' || rule
             || ' | score=' || score
             || ' | mode=' || mode
      FROM moderation_log ORDER BY ts DESC LIMIT $N;
    "
}

cmd_chats() {
    echo -e "${BOLD}${MAUVE}=== Chats ===${NC}\n"
    run_sql "
      SELECT CASE WHEN am_admin=1 THEN '✅' ELSE '❌' END
             || ' ' || chat_id || ' | ' || COALESCE(title,'?')
             || ' (' || type || ')'
             || ' restrict=' || can_restrict
             || ' delete=' || can_delete
      FROM bot_chats ORDER BY am_admin DESC, title;
    "
}

cmd_bans() {
    echo -e "${BOLD}${MAUVE}=== Banneados activos ===${NC}\n"
    run_sql "
      SELECT user_id || ' | ' || rule
             || ' | ' || strftime('%m-%d %H:%M', banned_at, 'unixepoch', 'localtime')
             || ' | ' || SUBSTR(reason, 1, 60)
      FROM banned_users WHERE revoked_at IS NULL ORDER BY banned_at DESC LIMIT 50;
    "
}

cmd_shadow() {
    [ -f .env ] || { echo -e "${RED}.env no existe${NC}"; return 1; }
    sed -i 's/^MODE=.*/MODE=shadow/' .env
    echo -e "${YELLOW}MODE=shadow${NC}"
    cmd_restart
}

cmd_active() {
    [ -f .env ] || { echo -e "${RED}.env no existe${NC}"; return 1; }
    echo -e "${RED}${BOLD}⚠️  Modo ACTIVE: acciones REALES (ban/kick/delete).${NC}"
    read -p "¿Confirmar? (escribe 'si'): " ans
    [ "$ans" = "si" ] || { echo "Cancelado."; return 1; }
    sed -i 's/^MODE=.*/MODE=active/' .env
    cmd_restart
}

cmd_test() {
    container_running || { echo -e "${YELLOW}Levantando para tests...${NC}"; docker compose up -d --build; sleep 2; }
    docker exec "$CONTAINER" python -m pytest /app/src/../tests -v 2>&1 || \
        docker exec -e PYTHONPATH=/app "$CONTAINER" sh -c "cd /app && python -m pytest tests -v"
}

cmd_analyze() {
    container_running || { echo -e "${RED}El bot debe estar corriendo${NC}"; return 1; }
    local extra=""
    case "$1" in
        ban) extra="--ban-cas" ;;
        deep) extra="--aggressive" ;;
    esac
    if ! grep -qE '^TG_API_ID=.+' .env 2>/dev/null || ! grep -qE '^TG_API_HASH=.+' .env 2>/dev/null; then
        echo -e "${RED}Faltan TG_API_ID / TG_API_HASH / TG_PHONE en .env${NC}"
        echo -e "${YELLOW}Sácalos de https://my.telegram.org → API development tools${NC}"
        return 1
    fi
    docker exec -it -e PYTHONPATH=/app "$CONTAINER" python -m scripts.analyze_members $extra
}

case "${1:-help}" in
    up|start) cmd_up ;;
    down|stop) cmd_down ;;
    restart) cmd_restart ;;
    rebuild) cmd_rebuild ;;
    status) cmd_status ;;
    logs|log) cmd_logs "$2" ;;
    follow|tail) cmd_follow ;;
    stats) cmd_stats ;;
    recent) cmd_recent "$2" ;;
    chats) cmd_chats ;;
    bans) cmd_bans ;;
    shadow) cmd_shadow ;;
    active) cmd_active ;;
    test|tests) cmd_test ;;
    analyze) cmd_analyze "" ;;
    analyze-ban) cmd_analyze ban ;;
    analyze-deep) cmd_analyze deep ;;
    help|--help|-h|*) show_help ;;
esac
