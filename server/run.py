"""Entry point for the API.

Runs plain HTTP for local dev. TLS termination via uvicorn's ssl args
will be wired in once we have certs for 1bit2qbit.theburkenator.com.
"""

import os

import uvicorn

from server.api.config import config
from server.api.database.db import Base, engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    print("Database schema created.")


def main() -> None:
    cert = os.environ.get("TLS_CERT_FILE")
    key = os.environ.get("TLS_KEY_FILE")

    if bool(cert) != bool(key):
        raise SystemExit("TLS_CERT_FILE and TLS_KEY_FILE must both be set or both be unset")

    uvicorn.run(
        "server.api.main:app",
        host=config.services.backend.host,
        port=config.services.backend.internal_port,
        ssl_certfile=cert,
        ssl_keyfile=key,
    )


if __name__ == "__main__":
    main()
