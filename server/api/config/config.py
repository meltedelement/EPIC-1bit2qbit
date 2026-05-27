"""Backend config.

Loads config.toml into nested pydantic models. To add a new config value,
add it to config.toml and add the corresponding field to the model — the
loader itself never needs to change.
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel


_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.toml"


class DbConfig(BaseModel):
    url: str


class BackendConfig(BaseModel):
    internal_port: int
    external_port: int
    host: str
    db: DbConfig


class WebAppConfig(BaseModel):
    internal_port: int


class ServicesConfig(BaseModel):
    web_app: WebAppConfig
    backend: BackendConfig


class NetworkConfig(BaseModel):
    external_host: str
    vm_address: str


class Config(BaseModel):
    network: NetworkConfig
    services: ServicesConfig


def _load() -> Config:
    try:
        with _CONFIG_PATH.open("rb") as f:
            data = tomllib.load(f)
        return Config.model_validate(data)
    except FileNotFoundError:
        raise FileNotFoundError(f"Server config not found: {_CONFIG_PATH}") from None
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Invalid TOML in {_CONFIG_PATH}: {e}") from e


config = _load()
