"""Entry point for the API.

Runs plain HTTP for local dev. TLS termination via uvicorn's ssl args
will be wired in once we have certs for 1bit2qbit.theburkenator.com.
"""

import os

import uvicorn

from app import config


def main() -> None:
    cert = os.environ.get("TLS_CERT_FILE")
    key = os.environ.get("TLS_KEY_FILE")

    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        ssl_certfile=cert,
        ssl_keyfile=key,
    )


if __name__ == "__main__":
    main()
