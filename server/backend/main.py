import logging

import uvicorn
from fastapi import FastAPI

from .config.config import config
from .database.db import Base, engine
from .logger import setup_logging
from .routes import auth, ws

setup_logging(config.model_dump())
logger = logging.getLogger(__name__)

app = FastAPI(title="1bit2qbit", version="0.1.0")
app.include_router(auth.router)
app.include_router(ws.router)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    print("Database schema created.")


def main() -> None:
    uvicorn.run(
        "backend.main:app",
        host=config.services.backend.host,
        port=config.services.backend.internal_port,
        root_path="/backend",
    )


if __name__ == "__main__":
    main()
