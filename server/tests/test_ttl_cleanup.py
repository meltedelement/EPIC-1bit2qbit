import asyncio
from contextlib import suppress
from unittest.mock import MagicMock, patch

from backend.daemons.ttl_cleanup import _run_cleanup, loop
from ws_helpers import _session_cm

_TTL_SL = "backend.daemons.ttl_cleanup.SessionLocal"
_TTL_SLEEP = "backend.daemons.ttl_cleanup.asyncio.sleep"


def _db(delete_count=0):
    db = MagicMock()
    db.query.return_value.filter.return_value.delete.return_value = delete_count
    return db


def _run_loop(coro):
    """Run an async loop coroutine until it raises CancelledError."""
    with suppress(asyncio.CancelledError):
        asyncio.run(coro)


class TestRunCleanup:
    def test_no_expired_rows_returns_zero(self):
        with patch(_TTL_SL, return_value=_session_cm(_db(0))):
            assert _run_cleanup() == 0

    def test_expired_rows_returns_count(self):
        with patch(_TTL_SL, return_value=_session_cm(_db(5))):
            assert _run_cleanup() == 5

    def test_delete_called_with_synchronize_session_false(self):
        db = _db()
        with patch(_TTL_SL, return_value=_session_cm(db)):
            _run_cleanup()
        db.query.return_value.filter.return_value.delete.assert_called_once_with(
            synchronize_session=False
        )

    def test_commit_called_after_successful_delete(self):
        db = _db(delete_count=3)
        with patch(_TTL_SL, return_value=_session_cm(db)):
            _run_cleanup()
        db.commit.assert_called_once()

    def test_commit_not_called_when_delete_raises(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.delete.side_effect = Exception("db error")
        with patch(_TTL_SL, return_value=_session_cm(db)):
            try:
                _run_cleanup()
            except Exception:
                pass
        db.commit.assert_not_called()


class TestCleanupLoop:
    def test_db_failure_is_caught_and_loop_retries(self):
        """A DB error must not kill the loop — next cycle should still run."""
        sleep_calls = 0

        async def fake_sleep(_):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        with patch("backend.daemons.ttl_cleanup._run_cleanup", side_effect=[Exception("db down"), 0]):
            with patch(_TTL_SLEEP, side_effect=fake_sleep):
                _run_loop(loop())

        assert sleep_calls == 2

    def test_sleep_called_after_successful_run(self):
        async def fake_sleep(_):
            raise asyncio.CancelledError

        with patch("backend.daemons.ttl_cleanup._run_cleanup", return_value=4):
            with patch(_TTL_SLEEP, side_effect=fake_sleep) as mock_sleep:
                _run_loop(loop())

        mock_sleep.assert_called_once()

    def test_sleep_called_after_failure(self):
        """Sleep (and therefore retry) must happen even when _run_cleanup raises."""
        async def fake_sleep(_):
            raise asyncio.CancelledError

        with patch("backend.daemons.ttl_cleanup._run_cleanup", side_effect=Exception("db down")):
            with patch(_TTL_SLEEP, side_effect=fake_sleep) as mock_sleep:
                _run_loop(loop())

        mock_sleep.assert_called_once()

    def test_cancellation_exits_loop_cleanly(self):
        """CancelledError from sleep must propagate out (not be swallowed)."""
        async def fake_sleep(_):
            raise asyncio.CancelledError

        with patch("backend.daemons.ttl_cleanup._run_cleanup", return_value=0):
            with patch(_TTL_SLEEP, side_effect=fake_sleep):
                import pytest
                with pytest.raises(asyncio.CancelledError):
                    asyncio.run(loop())
