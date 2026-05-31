#!/usr/bin/env bash
# Usage:
#   ./run.sh setup               Install Python & Node deps, build frontend, install nginx config
#   ./run.sh start               Start backend and verify (nginx)
#   ./run.sh start --backend     Start backend only
#   ./run.sh start --verify      Build frontend and start/reload nginx
#   ./run.sh stop                Stop all services
#   ./run.sh stop --backend      Stop backend only
#   ./run.sh stop --verify       Disable verify site and reload nginx
#   ./run.sh status              Show service status and URLs
#   ./run.sh logs                Tail all logs (backend + nginx)
#   ./run.sh logs --backend      Tail backend logs only
#   ./run.sh logs --verify       Tail nginx access/error logs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"
LOG_DIR="$SCRIPT_DIR/logs"
BACKEND_PID="$PID_DIR/backend.pid"
WEBAPP_DIST="$SCRIPT_DIR/web-app/dist"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info() { printf "${CYAN}[info]${RESET}  %s\n" "$*"; }
ok()   { printf "${GREEN}[ok]${RESET}    %s\n" "$*"; }
warn() { printf "${YELLOW}[warn]${RESET}  %s\n" "$*"; }
err()  { printf "${RED}[error]${RESET} %s\n" "$*" >&2; }
die()  { err "$*"; exit 1; }

# ── Helpers ───────────────────────────────────────────────────────────────────

activate_venv() {
    local v
    for v in .venv venv; do
        if [[ -f "$SCRIPT_DIR/$v/bin/activate" ]]; then
            # shellcheck disable=SC1090
            source "$SCRIPT_DIR/$v/bin/activate"
            return 0
        fi
    done
    warn "No virtual environment found (.venv/ or venv/) — using system Python"
}

load_env() {
    [[ -f "$SCRIPT_DIR/.env" ]] || return 0
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
}

# Prints the PID if the backend process is alive; returns 1 otherwise.
backend_pid() {
    [[ -f "$BACKEND_PID" ]] || return 1
    local pid
    pid=$(< "$BACKEND_PID")
    if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$BACKEND_PID"   # stale PID file
        return 1
    fi
    printf '%s' "$pid"
}

nginx_running() {
    systemctl is-active --quiet nginx 2>/dev/null
}

# Sets DO_BACKEND and DO_VERIFY based on flags; defaults to both if no flags given.
parse_flags() {
    DO_BACKEND=false
    DO_VERIFY=false
    local saw_flag=false
    while [[ $# -gt 0 ]]; do
        case $1 in
            --backend) DO_BACKEND=true; saw_flag=true ;;
            --verify)  DO_VERIFY=true;  saw_flag=true ;;
            *) die "Unknown flag: $1" ;;
        esac
        shift
    done
    if [[ "$saw_flag" == false ]]; then
        DO_BACKEND=true
        DO_VERIFY=true
    fi
}

# ── Service actions ───────────────────────────────────────────────────────────

start_backend() {
    local pid
    if pid=$(backend_pid 2>/dev/null); then
        warn "Backend already running (PID $pid)"
        return 0
    fi

    mkdir -p "$PID_DIR" "$LOG_DIR"
    activate_venv
    load_env

    info "Starting backend…"
    nohup epic-api >> "$LOG_DIR/backend.stdout.log" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$BACKEND_PID"

    # Give the process a moment to detect an immediate crash
    sleep 1
    if ! kill -0 "$new_pid" 2>/dev/null; then
        rm -f "$BACKEND_PID"
        die "Backend crashed at startup — check $LOG_DIR/backend.stdout.log"
    fi
    ok "Backend started (PID $new_pid)"
    printf "    internal  http://127.0.0.1:8443\n"
    printf "    external  https://1bit2qbit.theburkenator.com/backend/\n"
    printf "    api docs  https://1bit2qbit.theburkenator.com/backend/docs\n"
}

start_verify() {
    info "Building frontend…"
    cd "$SCRIPT_DIR/web-app"
    npm run build
    cd "$SCRIPT_DIR"
    ok "Frontend built → web-app/dist/"

    info "Enabling verify site…"
    sudo ln -sf /etc/nginx/sites-available/1bit2qbit /etc/nginx/sites-enabled/1bit2qbit
    if nginx_running; then
        sudo systemctl reload nginx
    else
        sudo systemctl start nginx
    fi
    ok "Verify started → https://1bit2qbit.theburkenator.com/verify/"
}

stop_backend() {
    local pid
    if pid=$(backend_pid 2>/dev/null); then
        info "Stopping backend (PID $pid)…"
        kill "$pid"
        rm -f "$BACKEND_PID"
        ok "Backend stopped"
    else
        warn "Backend is not running"
    fi
}

stop_verify() {
    if [[ -L /etc/nginx/sites-enabled/1bit2qbit ]]; then
        info "Disabling verify site…"
        sudo rm -f /etc/nginx/sites-enabled/1bit2qbit
        sudo systemctl reload nginx
        ok "Verify stopped"
    else
        warn "Verify is not enabled"
    fi
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd_setup() {
    # Create a virtual environment if neither .venv nor venv exists
    local venv_found=false
    for v in .venv venv; do
        [[ -f "$SCRIPT_DIR/$v/bin/activate" ]] && venv_found=true && break
    done
    if [[ "$venv_found" == false ]]; then
        info "Creating Python virtual environment (.venv)…"
        python3 -m venv "$SCRIPT_DIR/.venv"
        ok "Virtual environment created"
    fi

    info "Installing Python dependencies…"
    activate_venv
    pip install -e ".[dev]" -q
    ok "Python dependencies installed"

    info "Installing Node dependencies…"
    cd "$SCRIPT_DIR/web-app"
    npm install --silent
    ok "Node dependencies installed"

    info "Building frontend…"
    npm run build
    cd "$SCRIPT_DIR"
    ok "Frontend built → web-app/dist/"

    # Warn if the nginx.conf alias path doesn't match where we actually are
    local expected_alias="$WEBAPP_DIST/"
    local conf_alias
    conf_alias=$(sed -n 's/.*alias[[:space:]]\+\(.*\);/\1/p' "$SCRIPT_DIR/nginx.conf" | head -1)
    if [[ -n "$conf_alias" && "$conf_alias" != "$expected_alias" ]]; then
        warn "nginx.conf alias path does not match actual dist location:"
        warn "  conf has:  $conf_alias"
        warn "  should be: $expected_alias"
        warn "Update the alias line in server/nginx.conf before reloading nginx."
    fi

    info "Installing nginx config…"
    sudo cp "$SCRIPT_DIR/nginx.conf" /etc/nginx/sites-available/1bit2qbit
    sudo ln -sf /etc/nginx/sites-available/1bit2qbit /etc/nginx/sites-enabled/1bit2qbit
    # Remove the default site so it doesn't conflict on port 80
    sudo rm -f /etc/nginx/sites-enabled/default
    sudo nginx -t
    ok "nginx config installed and validated"

    printf "\n"
    ok "Setup complete — run ./run.sh start to launch all services"
}

cmd_start() {
    parse_flags "$@"
    if [[ "$DO_BACKEND" == true ]]; then start_backend; fi
    if [[ "$DO_VERIFY"  == true ]]; then start_verify;  fi
}

cmd_stop() {
    parse_flags "$@"
    if [[ "$DO_BACKEND" == true ]]; then stop_backend; fi
    if [[ "$DO_VERIFY"  == true ]]; then stop_verify;  fi
}

cmd_status() {
    printf "\n${BOLD}%-10s  %-14s  %s${RESET}\n" "SERVICE" "STATUS" "URL"
    printf '%.0s─' {1..62}; printf '\n'

    local pid
    if pid=$(backend_pid 2>/dev/null); then
        printf "%-10s  ${GREEN}%-14s${RESET}  %s\n" \
            "backend" "running ($pid)" "https://1bit2qbit.theburkenator.com/backend/"
    else
        printf "%-10s  ${RED}%-14s${RESET}\n" "backend" "stopped"
    fi

    if nginx_running; then
        printf "%-10s  ${GREEN}%-14s${RESET}  %s\n" \
            "verify" "running" "https://1bit2qbit.theburkenator.com/verify/"
    else
        printf "%-10s  ${RED}%-14s${RESET}\n" "verify" "stopped"
    fi

    printf '%.0s─' {1..62}; printf '\n'

    if [[ ! -d "$WEBAPP_DIST" ]]; then
        warn "Frontend not built — run ./run.sh setup"
    fi
    printf '\n'
}

cmd_logs() {
    parse_flags "$@"

    # Collect backend log files: structured logs first, then stdout capture
    local backend_files=()
    if [[ "$DO_BACKEND" == true ]]; then
        mkdir -p "$LOG_DIR"
        while IFS= read -r -d '' f; do
            backend_files+=("$f")
        done < <(find "$LOG_DIR" -maxdepth 1 -name "*.log" \
                     -not -name "backend.stdout.log" -print0 2>/dev/null | sort -z)
        if [[ -f "$LOG_DIR/backend.stdout.log" ]]; then
            backend_files+=("$LOG_DIR/backend.stdout.log")
        fi
        if [[ ${#backend_files[@]} -eq 0 ]]; then
            warn "No backend log files found yet — has the backend been started?"
        fi
    fi

    local nginx_logs=(/var/log/nginx/access.log /var/log/nginx/error.log)

    if [[ "$DO_BACKEND" == true && "$DO_VERIFY" == true ]]; then
        info "Tailing all logs — Ctrl+C to stop"
        # Kill background jobs on exit
        trap 'kill $(jobs -p) 2>/dev/null; exit' INT TERM EXIT
        if [[ ${#backend_files[@]} -gt 0 ]]; then
            tail -F "${backend_files[@]}" &
        fi
        sudo tail -F "${nginx_logs[@]}" &
        wait
    elif [[ "$DO_BACKEND" == true ]]; then
        if [[ ${#backend_files[@]} -eq 0 ]]; then exit 0; fi
        info "Tailing backend logs — Ctrl+C to stop"
        exec tail -F "${backend_files[@]}"
    else
        info "Tailing nginx logs — Ctrl+C to stop"
        exec sudo tail -F "${nginx_logs[@]}"
    fi
}

usage() {
    cat <<'EOF'
Usage: ./run.sh <command> [flags]

Commands:
  setup                 Install Python & Node deps, build frontend, install nginx config
  start                 Start backend and verify (nginx)
  start --backend       Start backend only
  start --verify        Build frontend and start/reload nginx
  stop                  Stop all services
  stop --backend        Stop backend only
  stop --verify         Disable verify site and reload nginx
  status                Show service status and URLs
  logs                  Tail all logs (backend + nginx)
  logs --backend        Tail backend logs only
  logs --verify         Tail nginx access/error logs
EOF
}

# ── Entry point ───────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR"

case "${1:-}" in
    setup)  shift; cmd_setup          ;;
    start)  shift; cmd_start  "$@"    ;;
    stop)   shift; cmd_stop   "$@"    ;;
    status) shift; cmd_status         ;;
    logs)   shift; cmd_logs   "$@"    ;;
    *)             usage; exit 1      ;;
esac
