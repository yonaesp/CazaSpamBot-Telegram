#!/usr/bin/env bash
# CazaSpamBot updater: installs the latest version and, if the bot doesn't start
# properly, goes back to the one you had. Run ./update.sh --help.
#
# Works with both kinds of install:
#   - from source (a git clone): follows your branch, `stable` (releases) or `main`;
#   - from the published image (no .git here): pulls the new image.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"
DIR=$PWD
SERVICE=antispam-bot
UNIT=cazaspambot-update
FAILED_FILE=.update-failed
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-240}   # seconds the new version gets to prove it's alive
HEALTH_MIN_UP=${HEALTH_MIN_UP:-31}      # two heartbeats (one every 30 s): it got past startup
HEALTH_POLL=${HEALTH_POLL:-5}

case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in es*) ES=1 ;; *) ES=0 ;; esac
say() { if [ "$ES" = 1 ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
die() { say "$1" "$2" >&2; exit "${3:-1}"; }

usage() {
    if [ "$ES" = 1 ]; then cat <<'EOF'
Uso: ./update.sh [opción]

  (sin opción)   Instala la última versión, si hay una (pregunta antes)
  --check        Solo dice si hay una versión nueva (código 10 si la hay)
  --yes, -y      Instala sin preguntar
  --auto         Activa la actualización automática cada noche
  --no-auto      La desactiva
  --unattended   Lo que hace la actualización automática: sin preguntar,
                 sin saltar de versión mayor ni repetir una que ya falló

Antes de reiniciar copia la base de datos en data/backups/. Si la versión nueva
no arranca bien en 4 minutos, vuelve sola a la que tenías.
EOF
    else cat <<'EOF'
Usage: ./update.sh [option]

  (no option)    Install the latest version, if there is one (asks first)
  --check        Only tell whether a new version is out (exit code 10 if so)
  --yes, -y      Install without asking
  --auto         Turn on automatic updates every night
  --no-auto      Turn them off
  --unattended   What the automatic update runs: no questions, no jumping to a
                 new major version and no retrying a version that already failed

It backs up the database to data/backups/ before restarting. If the new version
doesn't start properly within 4 minutes, it goes back to the one you had.
EOF
    fi
}

ACTION=update YES=0 UNATTENDED=0
case "${1:-}" in
    "") ;;
    --check) ACTION=check ;;
    --yes|-y) YES=1 ;;
    --unattended) YES=1 UNATTENDED=1 ;;
    --auto) ACTION=auto ;;
    --no-auto) ACTION=noauto ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 1 ;;
esac

[ -f docker-compose.yml ] || die "No docker-compose.yml here: run this from the bot's folder." \
    "No hay docker-compose.yml aquí: ejecútalo desde la carpeta del bot."

if [ -d .git ]; then MODE=source; else MODE=image; fi

# ------------------------------------------------------------------ engine
# Who runs the containers: docker (with sudo if your user can't) or podman
# (rootless as your user). COMPOSE and ENGINE override the detection.
detect_engine() {
    if [ -n "${COMPOSE:-}" ]; then
        read -ra COMPOSE_CMD <<<"$COMPOSE"
        read -ra ENGINE_CMD <<<"${ENGINE:-docker}"
        return
    fi
    local sudo=()
    if command -v docker >/dev/null 2>&1; then
        if [ "$(id -u)" != 0 ] && ! docker info >/dev/null 2>&1; then sudo=(sudo); fi
        if "${sudo[@]}" docker compose version >/dev/null 2>&1; then
            COMPOSE_CMD=("${sudo[@]}" docker compose)
        elif command -v docker-compose >/dev/null 2>&1; then
            COMPOSE_CMD=("${sudo[@]}" docker-compose)
        else
            die "Docker is installed but 'docker compose' isn't." "Docker está instalado, pero 'docker compose' no."
        fi
        ENGINE_CMD=("${sudo[@]}" docker)
    elif command -v podman >/dev/null 2>&1; then
        if podman compose version >/dev/null 2>&1; then COMPOSE_CMD=(podman compose)
        elif command -v podman-compose >/dev/null 2>&1; then COMPOSE_CMD=(podman-compose)
        else die "Podman is installed but 'podman compose' isn't." "Podman está instalado, pero 'podman compose' no."
        fi
        ENGINE_CMD=(podman)
    else
        die "Neither Docker nor Podman found." "No encuentro Docker ni Podman."
    fi
}

# Git runs as the folder's owner even from the root timer: otherwise root would
# leave files in .git that your user can't touch.
OWNER=$(stat -c %U .)
as_owner() {
    if [ "$(id -u)" = 0 ] && [ "$OWNER" != root ]; then runuser -u "$OWNER" -- "$@"; else "$@"; fi
}
git_() { as_owner git "$@"; }

# ------------------------------------------------------------------ versions
version_of() {  # version_of <git rev>  → v1.2.3 (or "")
    git_ show "$1:src/version.py" 2>/dev/null | sed -n 's/^__version__ = "\(.*\)"/v\1/p'
}
image_version() {  # image_version <image id> → v1.2.3 (or "")
    local v
    v=$("${ENGINE_CMD[@]}" image inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' "$1" 2>/dev/null || true)
    case "$v" in ""|"<no value>") ;; v*) printf '%s' "$v" ;; *) printf 'v%s' "$v" ;; esac
}
major() { local v=${1#v}; printf '%s' "${v%%.*}"; }

# ------------------------------------------------------------------ the bot
exec_bot() { "${COMPOSE_CMD[@]}" exec -T "$SERVICE" "$@"; }

# Database backup and a note for the bot that starts next, so it can tell you
# whether the new version stayed or it went back. Only if the bot is running.
before_restart() {  # before_restart <from> <to>
    local code
    code='
import glob, json, os, sqlite3, sys, time
os.makedirs("/app/data/backups", exist_ok=True)
dest = time.strftime("/app/data/backups/preupdate-%Y%m%d-%H%M%S.db")
sqlite3.connect("/app/data/antispam.db").execute("VACUUM INTO ?", (dest,))
for old in sorted(glob.glob("/app/data/backups/preupdate-*.db"))[:-3]:
    os.remove(old)
with open("/app/data/update-pending.json", "w") as f:
    json.dump({"from": sys.argv[1], "to": sys.argv[2], "ts": int(time.time())}, f)
print(os.path.basename(dest))
'
    local copy
    if copy=$(exec_bot python -c "$code" "$1" "$2" 2>/dev/null); then
        say "Database backed up: data/backups/$copy" "Base de datos copiada: data/backups/$copy"
    else
        say "The bot isn't running: updating without a database backup." \
            "El bot no está en marcha: actualizo sin copiar la base de datos."
    fi
}

# Healthy = the bot wrote its heartbeat (data/heartbeat, every 30 s) at least
# HEALTH_MIN_UP seconds after the new container started.
wait_healthy() {  # wait_healthy <start epoch>
    local deadline=$(( $(date +%s) + HEALTH_TIMEOUT )) beat
    while [ "$(date +%s)" -lt "$deadline" ]; do
        beat=$(stat -c %Y data/heartbeat 2>/dev/null || echo 0)
        [ "$beat" -ge $(( $1 + HEALTH_MIN_UP )) ] && return 0
        sleep "$HEALTH_POLL"
    done
    return 1
}

start_bot() {  # recreate the container and wait for it
    local t0
    if [ "$MODE" = source ]; then
        "${COMPOSE_CMD[@]}" up -d --build --force-recreate "$SERVICE" || return 1
    else
        "${COMPOSE_CMD[@]}" up -d --force-recreate "$SERVICE" || return 1
    fi
    t0=$(date +%s)
    say "Waiting for the bot to start (up to $(( HEALTH_TIMEOUT / 60 )) min)..." \
        "Esperando a que arranque el bot (hasta $(( HEALTH_TIMEOUT / 60 )) min)..."
    wait_healthy "$t0"
}

# Last resort, when even the old version won't start: tell the admin directly,
# since the bot can't. The token goes through stdin, never on the command line.
alert_admin() {
    local token chat
    token=$(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' .env 2>/dev/null | tail -n1 | tr -d "\"' \r")
    chat=$(sed -n 's/^ADMIN_NOTIFY_CHAT_ID=//p' .env 2>/dev/null | tail -n1 | tr -d "\"' \r")
    [ -n "$chat" ] || chat=$(sed -n 's/^ADMIN_USER_ID=//p' .env 2>/dev/null | tail -n1 | tr -d "\"' \r")
    [ -n "$token" ] && [ -n "$chat" ] && command -v curl >/dev/null 2>&1 || return 0
    printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$token" |
        curl -sS -o /dev/null --max-time 20 -K - --data-urlencode "chat_id=$chat" \
            --data-urlencode "text=$1" || true
}

# ------------------------------------------------------------------ automatic
unit_files() {
    cat >"$1/$UNIT.service" <<EOF
[Unit]
Description=CazaSpamBot automatic update
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$DIR/update.sh --unattended
EOF
    cat >"$1/$UNIT.timer" <<EOF
[Unit]
Description=CazaSpamBot automatic update, every night

[Timer]
OnCalendar=*-*-* 04:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF
}

auto_on() {
    if [ "$MODE" = source ] && [ "$(git_ symbolic-ref --short -q HEAD || true)" != stable ]; then
        die "Automatic updates follow the stable releases. Switch first with: git checkout stable" \
            "Las actualizaciones automáticas siguen las versiones estables. Cámbiate antes con: git checkout stable"
    fi
    local systemctl=${SYSTEMCTL:-systemctl}
    if [ -z "${UNIT_DIR:-}" ] && [ ! -d /run/systemd/system ]; then
        say "No systemd here. Add this line with 'crontab -e' (as root if you use sudo for docker):" \
            "Aquí no hay systemd. Añade esta línea con 'crontab -e' (como root si usas sudo con docker):"
        echo "0 4 * * * $DIR/update.sh --unattended >> $DIR/update.log 2>&1"
        return
    fi
    local tmp; tmp=$(mktemp -d); unit_files "$tmp"
    if [ "${ENGINE_CMD[0]}" = podman ] && [ "$(id -u)" != 0 ]; then
        # Rootless Podman: the containers are your user's, and so is the timer.
        local dir=${UNIT_DIR:-$HOME/.config/systemd/user}
        mkdir -p "$dir" && cp "$tmp/$UNIT".* "$dir/"
        $systemctl --user daemon-reload && $systemctl --user enable --now "$UNIT.timer"
        if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != yes ]; then
            say "To run while you're logged out: loginctl enable-linger $USER" \
                "Para que funcione sin tener la sesión abierta: loginctl enable-linger $USER"
        fi
    else
        local dir=${UNIT_DIR:-/etc/systemd/system} sudo=()
        [ "$(id -u)" = 0 ] || [ -n "${UNIT_DIR:-}" ] || sudo=(sudo)
        "${sudo[@]}" cp "$tmp/$UNIT".* "$dir/"
        "${sudo[@]}" $systemctl daemon-reload && "${sudo[@]}" $systemctl enable --now "$UNIT.timer"
    fi
    rm -rf "$tmp"
    say "Automatic updates on: every night between 04:00 and 05:00. The bot tells you in private how it went." \
        "Actualizaciones automáticas activadas: cada noche entre las 04:00 y las 05:00. El bot te cuenta por privado cómo ha ido."
}

auto_off() {
    local systemctl=${SYSTEMCTL:-systemctl} found=0 dir
    dir=${UNIT_DIR:-$HOME/.config/systemd/user}
    if [ -f "$dir/$UNIT.timer" ]; then
        $systemctl --user disable --now "$UNIT.timer" 2>/dev/null || true
        rm -f "$dir/$UNIT".*; $systemctl --user daemon-reload 2>/dev/null || true; found=1
    fi
    dir=${UNIT_DIR:-/etc/systemd/system}
    if [ -f "$dir/$UNIT.timer" ]; then
        local sudo=(); [ "$(id -u)" = 0 ] || [ -n "${UNIT_DIR:-}" ] || sudo=(sudo)
        "${sudo[@]}" $systemctl disable --now "$UNIT.timer" 2>/dev/null || true
        "${sudo[@]}" rm -f "$dir/$UNIT".*; "${sudo[@]}" $systemctl daemon-reload || true; found=1
    fi
    if [ "$found" = 1 ]; then say "Automatic updates off." "Actualizaciones automáticas desactivadas."
    else say "Automatic updates weren't on." "Las actualizaciones automáticas no estaban activadas."; fi
}

# ------------------------------------------------------------------ main
detect_engine
case "$ACTION" in
    auto) auto_on; exit 0 ;;
    noauto) auto_off; exit 0 ;;
esac

# One update at a time (the nightly one and yours could meet).
[ -e .update.lock ] || touch .update.lock
exec 9<.update.lock
command -v flock >/dev/null 2>&1 && ! flock -n 9 && \
    die "Another update is already running." "Ya hay otra actualización en marcha."

if [ "$MODE" = source ]; then
    BRANCH=$(git_ symbolic-ref --short -q HEAD || true)
    [ -n "$BRANCH" ] || die "You're not on a branch. Go back to yours, e.g.: git checkout stable" \
        "No estás en ninguna rama. Vuelve a la tuya, por ejemplo: git checkout stable"
    if ! git_ diff --quiet || ! git_ diff --cached --quiet; then
        die "You changed files that come with the bot (see 'git status'). Put your words in config/blacklist/custom/, or run: git stash && ./update.sh && git stash pop" \
            "Has cambiado ficheros que vienen con el bot (mira 'git status'). Pon tus palabras en config/blacklist/custom/, o haz: git stash && ./update.sh && git stash pop"
    fi
    git_ fetch --quiet --tags origin || die "Couldn't reach GitHub." "No he podido conectar con GitHub."
    git_ rev-parse -q --verify "origin/$BRANCH" >/dev/null || \
        die "There's no '$BRANCH' branch on GitHub to follow." "En GitHub no hay una rama '$BRANCH' que seguir."
    OLD=$(git_ rev-parse HEAD); NEW=$(git_ rev-parse "origin/$BRANCH")
    if [ "$OLD" = "$NEW" ] || git_ merge-base --is-ancestor "$NEW" "$OLD"; then
        say "Already up to date ($(version_of HEAD), branch $BRANCH)." \
            "Ya tienes la última ($(version_of HEAD), rama $BRANCH)."
        exit 0
    fi
    git_ merge-base --is-ancestor "$OLD" "$NEW" || \
        die "Your copy has commits that aren't on GitHub's '$BRANCH': update it by hand." \
            "Tu copia tiene commits que no están en la rama '$BRANCH' de GitHub: actualízala a mano."
    FROM=$(version_of "$OLD"); TO=$(version_of "$NEW")
    COUNT=$(git_ rev-list --count "$OLD..$NEW")
    say "New version: ${FROM:-?} → ${TO:-?} ($COUNT changes, branch $BRANCH)." \
        "Versión nueva: ${FROM:-?} → ${TO:-?} ($COUNT cambios, rama $BRANCH)."
else
    CID=$("${COMPOSE_CMD[@]}" ps -q "$SERVICE" 2>/dev/null | head -n1)
    [ -n "$CID" ] || die "The bot's container isn't there: start it with 'docker compose up -d'." \
        "No está el contenedor del bot: arráncalo con 'docker compose up -d'."
    REF=$("${ENGINE_CMD[@]}" inspect -f '{{.Config.Image}}' "$CID")
    OLD=$("${ENGINE_CMD[@]}" inspect -f '{{.Image}}' "$CID")
    "${COMPOSE_CMD[@]}" pull --quiet "$SERVICE" >/dev/null || die "Couldn't download the image." "No he podido descargar la imagen."
    NEW=$("${ENGINE_CMD[@]}" image inspect -f '{{.Id}}' "$REF")
    FROM=$(image_version "$OLD"); TO=$(image_version "$NEW")
    if [ "$OLD" = "$NEW" ]; then
        say "Already up to date (${FROM:-$REF})." "Ya tienes la última (${FROM:-$REF})."
        exit 0
    fi
    say "New version: ${FROM:-?} → ${TO:-?} ($REF)." "Versión nueva: ${FROM:-?} → ${TO:-?} ($REF)."
fi

[ "$ACTION" = check ] && exit 10

if [ "$UNATTENDED" = 1 ]; then
    if [ -n "$FROM" ] && [ -n "$TO" ] && [ "$(major "$TO")" != "$(major "$FROM")" ]; then
        say "$TO is a major version: install it by hand after reading what's new." \
            "$TO es una versión mayor: instálala a mano después de leer las novedades."
        exit 0
    fi
    if [ "$(cat "$FAILED_FILE" 2>/dev/null)" = "$NEW" ]; then
        say "That version already failed here once: skipping it." "Esa versión ya falló aquí una vez: no la repito."
        exit 0
    fi
fi

if [ "$YES" = 0 ]; then
    [ -t 0 ] || die "Not a terminal: use --yes to install without asking." "No es un terminal: usa --yes para instalar sin preguntar."
    read -r -p "$(say 'Install it now? The bot restarts for about a minute. [Y/n] ' '¿La instalo ya? El bot se reinicia durante un minuto. [S/n] ')" r
    case "$r" in ""|[YySs]*) ;; *) exit 0 ;; esac
fi

before_restart "${FROM:-?}" "${TO:-?}"

if [ "$MODE" = source ]; then
    git_ merge --ff-only --quiet "origin/$BRANCH"
fi

if start_bot; then
    rm -f "$FAILED_FILE"
    say "Done: running ${TO:-the new version}." "Hecho: ya funciona la ${TO:-versión nueva}."
    exit 0
fi

say "The new version didn't start properly: going back to ${FROM:-the previous one}." \
    "La versión nueva no arrancó bien: vuelvo a la ${FROM:-anterior}."
printf '%s\n' "$NEW" >"$FAILED_FILE"
if [ "$MODE" = source ]; then
    git_ reset --quiet --keep "$OLD"
else
    "${ENGINE_CMD[@]}" tag "$OLD" "$REF"
fi
if start_bot; then
    say "Back on ${FROM:-the previous version}. The bot will tell you in private." \
        "De vuelta en la ${FROM:-versión anterior}. El bot te lo contará por privado."
    exit 2
fi
alert_admin "⚠️ CazaSpamBot: the update to ${TO:-a new version} failed and so did going back to ${FROM:-the previous one}. The bot is down: run 'docker compose logs' in $DIR.

⚠️ CazaSpamBot: la actualización a la ${TO:-versión nueva} falló y también la vuelta a la ${FROM:-anterior}. El bot está parado: mira 'docker compose logs' en $DIR."
die "The previous version didn't start either: the bot is down. Look at: ${COMPOSE_CMD[*]} logs --tail 50" \
    "Tampoco arranca la versión anterior: el bot está parado. Mira: ${COMPOSE_CMD[*]} logs --tail 50" 3
