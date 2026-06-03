# EPIC-1bit2qbit — Secure End-to-End Encrypted Messaging

CS4455 Cybersecurity Epic Project 2026 · Team **1bit2qbit** · Immersive Software Engineering, 2nd Year

A secure messaging system that guarantees **confidentiality, integrity, and authenticity** of
communications against passive, active, honest-but-curious, and fully-compromised-server attackers.
The project spans all four CS4455 minors: secure networking, modern C++, cryptography, and blockchain.

**Repository:** <https://github.com/meltedelement/EPIC-1bit2qbit>

---

## Contents

- [Architecture at a glance](#architecture-at-a-glance)
- [How the four majors are covered](#how-the-four-majors-are-covered)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
  - [1. Server (FastAPI backend + verification web app)](#1-server-fastapi-backend--verification-web-app)
  - [2. Client (C++ binary + Python crypto subprocess)](#2-client-c-binary--python-crypto-subprocess)
  - [3. Blockchain (Solidity contract on Sepolia)](#3-blockchain-solidity-contract-on-sepolia)
- [Running the tests](#running-the-tests)
- [Documentation](#documentation)

---

## Architecture at a glance

```
┌────────────────────────── Client Application ──────────────────────────┐
│  C++ binary (epic-client)                Python crypto subprocess       │
│  • FTXUI terminal UI                      • X3DH key agreement          │
│  • Boost.Asio + raw OpenSSL TLS  ◄── JSON IPC ──►  • Double Ratchet     │
│  • manual WSS framing                    (stdin/stdout)  • AES-256-GCM  │
│  • SQLite message/key store               • Argon2id key derivation     │
└───────────────────────────────┬────────────────────────────────────────┘
                  HTTPS (register) │ WSS (login, messaging, key bundles)
┌───────────────────────────────▼────────────────────────────────────────┐
│  ISE Server (THEBURKENATOR.COM virtual host)                            │
│  • FastAPI: POST /register over HTTPS                                   │
│  • WebSocket router: auth, sessions, message queue, key-bundle directory│
│  • Argon2id password verification · rate limiting · MySQL store         │
│  • Background daemons: 30-day TTL cleanup + Merkle blockchain batching   │
│  • React/Vite verification web app (independent of the messaging app)   │
└───────────────────────────────┬────────────────────────────────────────┘
                                 │ recordBatch() / events
┌───────────────────────────────▼────────────────────────────────────────┐
│  Ethereum Sepolia — MessageIntegrity.sol                                │
│  Stores Merkle roots + timestamps for tamper-evident message integrity  │
└─────────────────────────────────────────────────────────────────────────┘
```

The server only relays **ciphertext** and metadata: it can never read message plaintext or
undetectably tamper with it, even when fully compromised. See
[`docs/design-decisions-cryptography.md`](docs/design-decisions-cryptography.md) for the threat model.

---

## How the four majors are covered

| Minor (25% each) | Where it lives | Summary |
|---|---|---|
| **Networking & Cybersecurity** | `client/src/connection/`, `server/backend/` | Raw OpenSSL TLS with CA-chain verification **and** certificate pinning; host-name resolution and async socket I/O via Boost.Asio; server-side Argon2id auth, rate limiting, input validation. Pen-test report in [`docs/security-tests/`](docs/security-tests/) and [`docs/security-assessment.md`](docs/security-assessment.md). |
| **C++ Programming** | `client/src/` | Multi-file C++ binary with `Client`, `User`, `Message`, `Conversation`, `MessageStore`, `Connection`, `CryptoProxy` classes; STL containers, RAII and smart pointers, CMake build. |
| **Cryptography** | `client/crypto_functions/`, `server/backend/crypto/` | X3DH + Double Ratchet, AES-256-GCM AEAD, HKDF domain separation, Argon2id password hashing and at-rest key encryption. Design doc: [`docs/design-decisions-cryptography.md`](docs/design-decisions-cryptography.md) and [`docs/report.pdf`](docs/report.pdf). |
| **Blockchain** | `blockchain/`, `server/web-app/` | `MessageIntegrity.sol` on Sepolia records keccak256 Merkle roots + timestamps; server batches digests; React verification page checks any message against the on-chain record. |

---

## Repository layout

```
EPIC-1bit2qbit/
├── client/            C++ binary + Python crypto subprocess (see client/README.md)
│   ├── src/           C++ sources (.h/.cpp): client, connection, crypto, messaging, models, ui
│   ├── crypto_functions/   Python: ratchet, x3dh, DEK, key management
│   ├── CMakeLists.txt / CMakePresets.json
│   └── subprocess_handler.py   JSON-over-stdio crypto IPC entry point
├── server/            FastAPI backend + React verification web app (see server/README.md)
│   ├── backend/       routes, handlers, auth, crypto, daemons, blockchain batcher
│   ├── web-app/       Vite/React on-chain verification SPA
│   ├── config.toml    network addresses, ports, MySQL socket URL
│   └── run.sh         setup / start / stop / status / logs orchestrator
├── blockchain/        Hardhat project — MessageIntegrity.sol + tests + deploy script
├── docs/              architecture, design decisions, flows, security + crypto reports
└── CLAUDE.md          contributor guidance
```

---

## Prerequisites

| Tool | Minimum | Used by |
|---|---|---|
| Python | 3.11 | server backend, client crypto subprocess |
| Node.js / npm | 18 / 9 | verification web app, blockchain |
| CMake + Ninja | 3.x | C++ client |
| A C++ toolchain | GCC 13+ / MinGW-w64 | C++ client |
| OpenSSL, Boost (Asio), SQLite3 | system libs | C++ client |
| MySQL | 8.0 | server backend (Unix-socket auth) |
| nginx | 1.18 | server reverse proxy |

The full backend runs on the team VM where MySQL is reachable over a Unix socket. Individual
components (client, blockchain, tests) build and run on any developer machine.

---

## Quick start

### 1. Server (FastAPI backend + verification web app)

The server is orchestrated by `server/run.sh`, which manages the FastAPI backend (uvicorn) and the
nginx-served React verification app. Full details and per-service controls are in
[`server/README.md`](server/README.md).

```bash
cd server
chmod +x run.sh

# First-time setup: creates the MySQL db/user, a Python .venv, installs Python + Node deps,
# builds the web app, and installs the nginx site config (idempotent).
./run.sh setup

# Day-to-day
./run.sh start     # start backend + nginx
./run.sh status    # show running state and URLs
./run.sh logs      # tail logs
./run.sh stop      # stop everything
```

> Manual equivalents (if you are not using `run.sh`): from `server/`, `pip install -e ".[dev]"`,
> initialise the schema, then launch the backend. The backend reads `server/config.toml` and expects
> the current working directory to be `server/`. TLS is enabled by setting the `TLS_CERT_FILE` and
> `TLS_KEY_FILE` environment variables. The blockchain batcher reads `SEPOLIA_RPC_URL`,
> `CONTRACT_ADDRESS`, and `PRIVATE_KEY` from `server/.env`.

### 2. Client (C++ binary + Python crypto subprocess)

The client is a C++ binary that spawns a Python crypto subprocess and talks to it over
newline-delimited JSON on stdin/stdout. Both halves must be built. Full instructions (including
Windows/MSYS2) are in [`client/README.md`](client/README.md).

**Build the C++ binary (Linux):**

```bash
sudo apt install build-essential cmake ninja-build libssl-dev libboost-dev libsqlite3-dev
cd client
cmake --preset linux-debug
cmake --build --preset linux-debug
# binary -> client/build/epic-client
```

**Set up the Python crypto subprocess (Python 3.11+):**

```bash
cd client
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run the binary from `client/` so it can locate `subprocess_handler.py` and the active virtualenv.

### 3. Blockchain (Solidity contract on Sepolia)

```bash
cd blockchain
npm install
npm run compile          # compile MessageIntegrity.sol
npm test                 # Hardhat test suite

# Deploy to the Sepolia testnet (needs blockchain/.env with the RPC URL + deployer key)
npm run deploy:sepolia
```

After deployment, set `CONTRACT_ADDRESS` in `server/.env` (and the address used by
`server/web-app/src/abi.json`) so the batcher and verification page target the deployed contract.
The compiled ABI consumed by the backend lives at `server/backend/blockchain/abi.json`.

---

## Running the tests

```bash
# Server (from repo root or server/)
python -m pytest server/tests -v

# Client crypto subprocess
cd client && pytest

# Blockchain
cd blockchain && npm test
```

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Mermaid diagrams for client and server module relationships |
| [`docs/server-flows.md`](docs/server-flows.md) | Step-by-step server flow sequences |
| [`docs/login-send-flow.md`](docs/login-send-flow.md) | Login and message-send walkthrough |
| [`docs/design-decisions.md`](docs/design-decisions.md) | Team design decisions |
| [`docs/design-decisions-cryptography.md`](docs/design-decisions-cryptography.md) | Threat model + cryptographic construction walkthrough |
| [`docs/security-assessment.md`](docs/security-assessment.md) · [`docs/security-tests/`](docs/security-tests/) | Vulnerability & penetration-testing report |
| [`docs/report.pdf`](docs/report.pdf) | Consolidated project report |
| [`client/README.md`](client/README.md) · [`server/README.md`](server/README.md) | Per-component build/run guides |
