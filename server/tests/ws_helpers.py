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
