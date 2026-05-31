# Server deployment

The `server/` directory contains two services managed by `run.sh`:

| Service | Description | URL |
|---|---|---|
| **backend** | FastAPI — registration, key bundles, message routing (uvicorn on `127.0.0.1:8443`) | `/backend/` |
| **verify** | React/Vite blockchain verification SPA (static files served by nginx) | `/verify/` |

nginx listens on port 80 and reverse-proxies both.

---

## Prerequisites

Install the following system packages before running `setup`.
On Ubuntu/Debian:

```bash
# Python 3.11+
sudo apt install python3.11 python3.11-venv python3-pip

# Node.js 18+ and npm
sudo apt install nodejs npm
# or via nvm: https://github.com/nvm-sh/nvm

# nginx
sudo apt install nginx
```

Minimum versions:

| Tool | Minimum |
|---|---|
| Python | 3.11 |
| pip | 23 |
| Node.js | 18 |
| npm | 9 |
| nginx | 1.18 |

---

## First-time setup

```bash
cd server
chmod +x run.sh
./run.sh setup
```

`setup` will:
1. Create a Python virtual environment (`.venv/`) if one doesn't exist
2. Install Python dependencies (`pip install -e ".[dev]"`)
3. Install Node dependencies and build the React frontend (`web-app/dist/`)
4. Copy `nginx.conf` to `/etc/nginx/sites-available/`, enable it, and validate it

---

## Daily usage

```bash
./run.sh start          # start backend + nginx
./run.sh stop           # stop all services
./run.sh status         # show running state and URLs
./run.sh logs           # tail all logs (Ctrl+C to stop)
./run.sh logs --backend # backend logs only
./run.sh logs --verify  # nginx access/error logs only
```

Individual services:

```bash
./run.sh start --backend   # backend only
./run.sh start --verify    # rebuild frontend and reload nginx
./run.sh stop  --backend
./run.sh stop  --verify
```

---

## Environment variables

Copy `.env.example` to `.env` before starting. Optional TLS variables:

| Variable | Description |
|---|---|
| `TLS_CERT_FILE` | Path to TLS certificate (both must be set together) |
| `TLS_KEY_FILE` | Path to TLS private key |
