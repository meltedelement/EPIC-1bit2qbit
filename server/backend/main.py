import logging
import os

import uvicorn
from fastapi import FastAPI
from logger import setup_logging

from .config.config import config
from .database.db import Base, engine
from .routes import auth

setup_logging(config.model_dump(), script_path=__file__)
logger = logging.getLogger(__name__)

app = FastAPI(title="1bit2qbit", version="0.1.0")
app.include_router(auth.router)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    print("Database schema created.")


def main() -> None:
    cert = os.environ.get("TLS_CERT_FILE")
    key = os.environ.get("TLS_KEY_FILE")

    if bool(cert) != bool(key):
        raise SystemExit("TLS_CERT_FILE and TLS_KEY_FILE must both be set or both be unset")

    uvicorn.run(
        "backend.main:app",
        host=config.services.backend.host,
        port=config.services.backend.internal_port,
        ssl_certfile=cert,
        ssl_keyfile=key,
    )


if __name__ == "__main__":
    main()
