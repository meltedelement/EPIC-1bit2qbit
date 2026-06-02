import asyncio
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.rate_limit import RateLimiter
from backend.session import SessionRegistry


def make_ws_app(router) -> tuple[FastAPI, TestClient]:
    app = FastAPI()
    app.state.sessions = SessionRegistry()
    app.state.rate_limiter = RateLimiter(max_window_seconds=900)
    app.include_router(router)
    return app, TestClient(app)


def _session_cm(db):
    """Wrap a mock db into a context manager that SessionLocal() can return."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=db)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _empty_drain():
    """Session mock where the offline queue drain returns nothing."""
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    return _session_cm(db)


class _CancelAfter:
    """Async sleep replacement that raises CancelledError after n calls."""

    def __init__(self, n=2):
        self.calls = 0
        self.n = n

    def __call__(self, _):
        self.calls += 1
        if self.calls >= self.n:
            raise asyncio.CancelledError
