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
NGINX_AVAILABLE=/etc/nginx/sites-available/1bit2qbit
NGINX_ENABLED=/etc/nginx/sites-enabled/1bit2qbit

# ── Helpers ───────────────────────────────────────────────────────────────────
info() { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
ok()   { echo -e "\033[1;32m[OK]\033[0m    $*"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
err()  { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; }
die()  { err "$*"; exit 1; }

activate_venv() {
    [[ -f "$SCRIPT_DIR/.venv/bin/activate" ]] || die "No virtual environment found — run ./run.sh setup first"
    source "$SCRIPT_DIR/.venv/bin/activate"
}

load_env() {
    [[ -f "$SCRIPT_DIR/.env" ]] || return 0
    set -a
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

nginx_reload() {
    if nginx_running; then
        sudo systemctl reload nginx
    else
        sudo systemctl start nginx
    fi
}

# Sets DO_BACKEND, DO_VERIFY, and REBUILD_VERIFY based on flags.
# REBUILD_VERIFY is false only when --backend is passed alone — every other
# combination that includes verify should rebuild the frontend.
parse_flags() {
    DO_BACKEND=false
    DO_VERIFY=false
    REBUILD_VERIFY=false
    local saw_flag=false
    while [[ $# -gt 0 ]]; do
        case $1 in
            --backend) DO_BACKEND=true; saw_flag=true ;;
            --verify)  DO_VERIFY=true; REBUILD_VERIFY=true; saw_flag=true ;;
            *) die "Unknown flag: $1" ;;
        esac
        shift
    done
    if [[ "$saw_flag" == false ]]; then
        DO_BACKEND=true
        DO_VERIFY=true
        REBUILD_VERIFY=true
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

    sleep 1 # Give the process a moment to detect an immediate crash
    if ! kill -0 "$new_pid" 2>/dev/null; then
        rm -f "$BACKEND_PID"
        die "Backend crashed at startup — check $LOG_DIR/backend.stdout.log"
    fi
    ok "Backend started (PID $new_pid)"
    info "internal  http://127.0.0.1:8000"
    info "external  https://1bit2qbit.theburkenator.com/backend/"
    info "api docs  https://1bit2qbit.theburkenator.com/backend/docs"
}

start_verify() {
    if [[ "$REBUILD_VERIFY" == true ]]; then
        info "Building frontend…"
        cd "$SCRIPT_DIR/web-app"
        npm run build
        cd "$SCRIPT_DIR"
        ok "Frontend built → web-app/dist/"
    fi

    if [[ ! -f "$NGINX_AVAILABLE" ]]; then
        die "nginx config not installed — run ./run.sh setup first"
    fi

    info "Enabling verify site…"
    sudo ln -sf "$NGINX_AVAILABLE" "$NGINX_ENABLED"
    sudo nginx -t
    nginx_reload
    ok "Verify started → https://1bit2qbit.theburkenator.com/verify/"
}

stop_backend() {
    local pid
    if pid=$(backend_pid 2>/dev/null); then
        info "Stopping backend (PID $pid)…"
        kill "$pid"
        local i
        for i in 1 2 3 4 5; do
            sleep 1
            if ! kill -0 "$pid" 2>/dev/null; then break; fi
        done
        if kill -0 "$pid" 2>/dev/null; then
            warn "Process did not exit after 5s — sending SIGKILL"
            kill -9 "$pid"
        fi
        rm -f "$BACKEND_PID"
        ok "Backend stopped"
    else
        warn "Backend is not running"
    fi
}

stop_verify() {
    if [[ -L "$NGINX_ENABLED" ]]; then
        info "Disabling verify site…"
        sudo rm -f "$NGINX_ENABLED"
        if nginx_running; then
            sudo systemctl reload nginx
        else
            warn "nginx is not running — verify disabled but no reload performed"
        fi
        ok "Verify stopped"
    else
        warn "Verify is not enabled"
    fi
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd_setup() {
    if [[ ! -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
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

    info "Installing nginx config…"
    # Substitute $WEBAPP_DIST into the alias line so the installed config is always
    # correct for this checkout location, regardless of what path is in the source file.
    local tmp
    tmp=$(mktemp)
    sed "s|alias [^;]*/web-app/dist/;|alias $WEBAPP_DIST/;|" "$SCRIPT_DIR/nginx.conf" > "$tmp"
    sudo cp "$tmp" $NGINX_AVAILABLE
    rm -f "$tmp"
    sudo ln -sf "$NGINX_AVAILABLE" "$NGINX_ENABLED"
    # Remove the default site so it doesn't conflict on port 80
    sudo rm -f /etc/nginx/sites-enabled/default
    sudo nginx -t
    ok "nginx config installed and validated"

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
    local pid
    if pid=$(backend_pid 2>/dev/null); then
        ok "backend  running ($pid) — https://1bit2qbit.theburkenator.com/backend/"
    else
        err "backend  stopped"
    fi

    if [[ -L "$NGINX_ENABLED" ]] && nginx_running; then
        ok "verify   running — https://1bit2qbit.theburkenator.com/verify/"
    else
        err "verify   stopped"
    fi

    if [[ ! -d "$WEBAPP_DIST" ]]; then
        warn "Frontend not built — run ./run.sh setup"
    fi
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
        trap 'kill $(jobs -p) 2>/dev/null || true; exit' INT TERM EXIT
        if [[ ${#backend_files[@]} -gt 0 ]]; then
            tail -F "${backend_files[@]}" &
        fi
        sudo -v  # cache credentials before backgrounding — avoids a prompt inside &
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
