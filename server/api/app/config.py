"""Backend config.

Shared deployment values live in ../config.toml so the web-app and the
API stay aligned on host/port/URL. Secrets (DB password, cert paths)
will move to env vars once we have real ones; for now there are none.
"""

import tomllib
from pathlib import Path


_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.toml"


def _load() -> dict:
    try:
        with _CONFIG_PATH.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Server config not found: {_CONFIG_PATH}") from None
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Invalid TOML in {_CONFIG_PATH}: {e}") from e


_cfg = _load()

host: str = _cfg["services"]["backend"]["host"]
port: int = _cfg["services"]["backend"]["internal_port"]
external_host: str = _cfg["network"]["external_host"]
db_url: str = _cfg["services"]["backend"]["db"]["url"]
