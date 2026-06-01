import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI

from .config.config import config
from .database.db import Base, engine
from .logger import setup_logging
from .routes import auth, ws
from .session import SessionRegistry

setup_logging(config.model_dump())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.sessions = SessionRegistry()
    logger.info("Session registry initialised")
    yield
    logger.info("Server shutting down")


app = FastAPI(title="1bit2qbit", version="0.1.0", lifespan=lifespan)
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
