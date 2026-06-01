# Client Build Guide

The client consists of two components that run together:

- **C++ binary** (`epic-client`) — terminal UI, networking, state management
- **Python subprocess** (`subprocess_handler.py`) — all cryptographic operations (X3DH, Double Ratchet, DEK management)

---

## C++ binary — Windows (MSYS2)

MinGW is a port of the GCC compiler to Windows. MSYS2 is the recommended distribution — it ships MinGW-w64 with a package manager (`pacman`) that provides pre-built Windows-native versions of all required libraries.

> The MSVC OpenSSL installer (`OpenSSL-Win64`) is **not compatible** with MinGW — its `lib/` only contains MSVC `.lib` files. Use the MSYS2 packages below instead.

**1. Install MSYS2**

```powershell
winget install MSYS2.MSYS2
```

**2. Open the MSYS2 MinGW x64 shell** from the Start menu and install the toolchain and dependencies:

```bash
pacman -Syu
pacman -S mingw-w64-x86_64-gcc \
          mingw-w64-x86_64-cmake \
          mingw-w64-x86_64-ninja \
          mingw-w64-x86_64-openssl \
          mingw-w64-x86_64-boost
```

**3. Build** (from the MSYS2 MinGW x64 shell):

```bash
cd /c/path/to/EPIC-1bit2qbit/client
cmake -B build
cmake --build build
```

The binary is written to `build/epic-client.exe`.

---

## C++ binary — Linux

```bash
sudo apt install build-essential cmake ninja-build libssl-dev libboost-dev
cd client
cmake -B build
cmake --build build
```

---

## Python crypto subprocess

Requires Python 3.11+.

```bash
cd client
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest
```

---

## Dependency summary

### C++ (CMake)

| Library | Version | Source |
|---|---|---|
| FTXUI | 5.0 | FetchContent (if not found locally) |
| nlohmann\_json | 3.11 | FetchContent (if not found locally) |
| CLI11 | 2.4 | FetchContent (if not found locally) |
| OpenSSL | any | System (MSYS2 or apt) |
| Boost | 1.74+ | System (MSYS2 or apt) — header-only, Asio |

### Python

| Package | Version |
|---|---|
| doubleratchet | ≥1.0.0 |
| x3dh | ≥1.3.0 |
| cryptography | ≥43 |
| argon2-cffi | ≥23.1 |
