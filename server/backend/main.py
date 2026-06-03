import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI

from .config.config import config
from .daemons import batcher, ttl_cleanup
from .database.db import Base, engine
from .logger import setup_logging
from .rate_limit import RateLimiter
from .routes import auth, ws
from .session import SessionRegistry

setup_logging(config.model_dump())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(Base.metadata.create_all, engine)
    logger.info("Database schema verified")

    application.state.sessions = SessionRegistry()
    logger.info("Session registry initialized")

    max_window = config.rate_limiting.ws_auth_fail_window_seconds
    application.state.rate_limiter = RateLimiter(max_window_seconds=max_window)
    logger.info("Rate limiter initialized")

    application.state.kb_limiter = RateLimiter(
        max_window_seconds=config.rate_limiting.kb_request_window_seconds
    )
    logger.info("Key bundle rate limiter initialized")

    batcher_task = asyncio.create_task(batcher.loop(), name="batcher")
    ttl_task = asyncio.create_task(ttl_cleanup.loop(), name="ttl-cleanup")

    yield

    batcher_task.cancel()
    ttl_task.cancel()
    with suppress(asyncio.CancelledError):
        await batcher_task
    logger.info("Batcher daemon stopped")
    with suppress(asyncio.CancelledError):
        await ttl_task
    logger.info("TTL cleanup daemon stopped")
    logger.info("Server shutting down")


app = FastAPI(title="1bit2qbit", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(ws.router)


def main() -> None:
    uvicorn.run(
        "backend.main:app",
        host=config.services.backend.host,
        port=config.services.backend.internal_port,
        root_path="/backend",
        log_config=None,
    )
