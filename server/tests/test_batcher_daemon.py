import asyncio
from contextlib import suppress
from unittest.mock import MagicMock, patch

from backend.daemons.batcher import _run_batch, loop
from ws_helpers import _session_cm

_BATCHER_SL = "backend.daemons.batcher.SessionLocal"
_ADD_TO_BC = "backend.daemons.batcher.add_to_blockchain"
_BATCHER_SLEEP = "backend.daemons.batcher.asyncio.sleep"

_BATCH_RESULT = [{"tx_hash": "0xabc", "root": "0xdef", "batch_index": 0, "leaf_count": 1}]


def _mock_row(id=1, mid="alice:bob:1000", ciphertext="ct"):
    row = MagicMock()
    row.id = id
    row.mid = mid
    row.ciphertext = ciphertext
    return row


def _read_db(rows):
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = rows
    return db


def _write_db():
    db = MagicMock()
    return db


def _run_loop(coro):
    with suppress(asyncio.CancelledError):
        asyncio.run(coro)


class TestRunBatch:
    def test_no_eligible_rows_returns_zero(self):
        with patch(_BATCHER_SL, return_value=_session_cm(_read_db([]))):
            with patch(_ADD_TO_BC) as mock_bc:
                assert _run_batch() == 0
        mock_bc.assert_not_called()

    def test_message_format_is_mid_colon_ciphertext(self):
        rows = [
            _mock_row(id=1, mid="alice:bob:1000", ciphertext="ct1"),
            _mock_row(id=2, mid="alice:carol:2000", ciphertext="ct2"),
        ]
        with patch(_BATCHER_SL, side_effect=[_session_cm(_read_db(rows)), _session_cm(_write_db())]):
            with patch(_ADD_TO_BC, return_value=_BATCH_RESULT) as mock_bc:
                _run_batch()
        assert mock_bc.call_args[0][0] == ["alice:bob:1000:ct1", "alice:carol:2000:ct2"]

    def test_returns_row_count_on_success(self):
        rows = [_mock_row(id=i) for i in range(3)]
        with patch(_BATCHER_SL, side_effect=[_session_cm(_read_db(rows)), _session_cm(_write_db())]):
            with patch(_ADD_TO_BC, return_value=_BATCH_RESULT):
                assert _run_batch() == 3

    def test_commit_called_after_successful_blockchain_submission(self):
        write_db = _write_db()
        with patch(_BATCHER_SL, side_effect=[_session_cm(_read_db([_mock_row()])), _session_cm(write_db)]):
            with patch(_ADD_TO_BC, return_value=_BATCH_RESULT):
                _run_batch()
        write_db.commit.assert_called_once()

    def test_blockchain_failure_does_not_open_delete_session(self):
        """If add_to_blockchain raises, the second DB session must never be opened."""
        sl_mock = MagicMock(side_effect=[_session_cm(_read_db([_mock_row()]))])
        with patch(_BATCHER_SL, sl_mock):
            with patch(_ADD_TO_BC, side_effect=Exception("on-chain revert")):
                try:
                    _run_batch()
                except Exception:
                    pass
        assert sl_mock.call_count == 1

    def test_blockchain_failure_propagates_to_caller(self):
        """The exception from add_to_blockchain must bubble up so the loop can catch it."""
        with patch(_BATCHER_SL, side_effect=[_session_cm(_read_db([_mock_row()]))]):
            with patch(_ADD_TO_BC, side_effect=ValueError("revert")):
                try:
                    _run_batch()
                    raised = False
                except ValueError:
                    raised = True
        assert raised

    def test_delete_uses_synchronize_session_false(self):
        write_db = _write_db()
        with patch(_BATCHER_SL, side_effect=[_session_cm(_read_db([_mock_row()])), _session_cm(write_db)]):
            with patch(_ADD_TO_BC, return_value=_BATCH_RESULT):
                _run_batch()
        write_db.query.return_value.filter.return_value.delete.assert_called_once_with(
            synchronize_session=False
        )


class TestBatcherLoop:
    def test_blockchain_failure_is_caught_and_loop_retries(self):
        """A blockchain error must not kill the loop — next cycle should still run."""
        sleep_calls = 0

        async def fake_sleep(_):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        with patch("backend.daemons.batcher._run_batch", side_effect=[Exception("revert"), 0]):
            with patch(_BATCHER_SLEEP, side_effect=fake_sleep):
                _run_loop(loop())

        assert sleep_calls == 2

    def test_sleep_called_after_successful_run(self):
        async def fake_sleep(_):
            raise asyncio.CancelledError

        with patch("backend.daemons.batcher._run_batch", return_value=3):
            with patch(_BATCHER_SLEEP, side_effect=fake_sleep) as mock_sleep:
                _run_loop(loop())

        mock_sleep.assert_called_once()

    def test_sleep_called_after_failure(self):
        """Interval sleep must happen even when _run_batch raises."""
        async def fake_sleep(_):
            raise asyncio.CancelledError

        with patch("backend.daemons.batcher._run_batch", side_effect=Exception("revert")):
            with patch(_BATCHER_SLEEP, side_effect=fake_sleep) as mock_sleep:
                _run_loop(loop())

        mock_sleep.assert_called_once()

    def test_cancellation_exits_loop_cleanly(self):
        import pytest

        async def fake_sleep(_):
            raise asyncio.CancelledError

        with patch("backend.daemons.batcher._run_batch", return_value=0):
            with patch(_BATCHER_SLEEP, side_effect=fake_sleep):
                with pytest.raises(asyncio.CancelledError):
                    asyncio.run(loop())
