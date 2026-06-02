import asyncio
from unittest.mock import MagicMock


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

    async def __call__(self, _):
        self.calls += 1
        if self.calls >= self.n:
            raise asyncio.CancelledError
