import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.database.models import BlockchainMessageQueue, KeyBundle, OneTimePreKey, User
from backend.routes.ws import router
from backend.session import SessionRegistry
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from ws_helpers import _session_cm

_app = FastAPI()
_app.state.sessions = SessionRegistry()
_app.include_router(router)
_client = TestClient(_app)

# Patch target shortcuts
_VERIFY = "backend.routes.ws.verify_credentials"
_MSG_SL = "backend.handlers.messaging.SessionLocal"
_KBD_SL = "backend.handlers.key_bundle.SessionLocal"


def _login_frame(username="alice"):
    return json.dumps({"username": username, "password": "irrelevant"})


def _messaging_db():
    """Baseline messaging mock: drain returns empty, scalar returns None."""
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    db.scalar.return_value = None
    return db


def _mock_bundle():
    b = MagicMock(spec=KeyBundle)
    b.identity_key = "ik_base64"
    b.signed_pre_key = "spk_base64"
    b.signed_pre_key_sig = "sig_base64"
    return b


def _mock_otpk():
    o = MagicMock(spec=OneTimePreKey)
    o.key_data = "otpk_base64"
    return o


def _mock_bmq(sender="alice", past_deadline=False):
    bmq = MagicMock(spec=BlockchainMessageQueue)
    bmq.sender_username = sender
    bmq.recipient_username = "bob"
    now = datetime.now(timezone.utc)
    bmq.edit_deadline = now - timedelta(minutes=1) if past_deadline else now + timedelta(minutes=10)
    return bmq


class TestFrameDispatch:
    def test_invalid_frame_type_returns_error_frame(self):
        msg_db = _messaging_db()
        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(json.dumps({"type": "not_a_real_type"}))
                    frame = json.loads(ws.receive_text())

        assert frame["type"] == "error"
        assert frame["code"] == "invalid_frame"

    def test_five_consecutive_bad_frames_close_4003(self):
        msg_db = _messaging_db()
        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    for _ in range(4):
                        ws.send_text("not json")
                        ws.receive_text()
                    ws.send_text("not json")
                    with pytest.raises(WebSocketDisconnect) as exc:
                        ws.receive_text()

        assert exc.value.code == 4003

    def test_good_frame_resets_error_counter(self):
        """4 bad + 1 good + 4 bad must not trigger the close threshold."""
        msg_db = _messaging_db()
        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    for _ in range(4):
                        ws.send_text("not json")
                        ws.receive_text()
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "send_message",
                                "recipient": "bob",
                                "ciphertext": "ct",
                                "mid": _valid_mid(),
                            }
                        )
                    )
                    ws.receive_text()  # unknown_recipient error
                    for _ in range(4):
                        ws.send_text("not json")
                        ws.receive_text()
                    # Connection still open — no exception raised


def _valid_mid(sender="alice", recipient="bob") -> str:
    return f"{sender}:{recipient}:{int(datetime.now(timezone.utc).timestamp() * 1000)}"


class TestSendMessage:
    def _frame(self, recipient="bob", ciphertext="encrypted", mid=None):
        return json.dumps(
            {
                "type": "send_message",
                "recipient": recipient,
                "ciphertext": ciphertext,
                "mid": mid if mid is not None else _valid_mid(recipient=recipient),
            }
        )

    def test_unknown_recipient_returns_error(self):
        msg_db = _messaging_db()
        msg_db.scalar.return_value = None

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame())
                    frame = json.loads(ws.receive_text())

        assert frame["type"] == "error"
        assert frame["code"] == "unknown_recipient"

    def test_offline_recipient_message_is_queued(self):
        msg_db = _messaging_db()
        msg_db.scalar.side_effect = [None, MagicMock(spec=User)]

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame())

        added = [type(c.args[0]).__name__ for c in msg_db.add.call_args_list]
        assert "BlockchainMessageQueue" in added
        assert "TTLDeliveryQueue" in added
        msg_db.commit.assert_called()

    def test_online_recipient_message_delivered(self):
        bob_ws = AsyncMock()
        msg_db = _messaging_db()
        msg_db.scalar.side_effect = [None, MagicMock(spec=User)]
        mid = _valid_mid()

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with patch.object(_app.state.sessions, "get", return_value=bob_ws):
                    with _client.websocket_connect("/ws") as ws:
                        ws.send_text(_login_frame())
                        ws.send_text(self._frame(mid=mid))

        bob_ws.send_text.assert_awaited_once()
        delivered = json.loads(bob_ws.send_text.call_args[0][0])
        assert delivered["type"] == "deliver_message"
        assert delivered["mid"] == mid
        assert delivered["sender"] == "alice"

    def test_online_delivery_failure_falls_back_to_queue(self):
        bob_ws = AsyncMock()
        bob_ws.send_text.side_effect = Exception("disconnected")
        msg_db = _messaging_db()
        msg_db.scalar.side_effect = [None, MagicMock(spec=User)]

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with patch.object(_app.state.sessions, "get", return_value=bob_ws):
                    with _client.websocket_connect("/ws") as ws:
                        ws.send_text(_login_frame())
                        ws.send_text(self._frame())

        added = [type(c.args[0]).__name__ for c in msg_db.add.call_args_list]
        assert "TTLDeliveryQueue" in added

    def test_online_recipient_does_not_write_to_ttl_queue(self):
        bob_ws = AsyncMock()
        msg_db = _messaging_db()
        msg_db.scalar.side_effect = [None, MagicMock(spec=User)]

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with patch.object(_app.state.sessions, "get", return_value=bob_ws):
                    with _client.websocket_connect("/ws") as ws:
                        ws.send_text(_login_frame())
                        ws.send_text(self._frame())

        added = [type(c.args[0]).__name__ for c in msg_db.add.call_args_list]
        assert "TTLDeliveryQueue" not in added

    def test_update_recipient_mismatch_returns_unauthorised(self):
        msg_db = _messaging_db()
        msg_db.scalar.return_value = _mock_bmq()  # recipient_username = "bob"

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame(recipient="carol"))  # different recipient
                    frame = json.loads(ws.receive_text())

        assert frame["type"] == "error"
        assert frame["code"] == "update_not_authorised"

    def test_update_wrong_sender_returns_mid_conflict(self):
        msg_db = _messaging_db()
        msg_db.scalar.return_value = _mock_bmq(sender="carol")

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame())
                    frame = json.loads(ws.receive_text())

        assert frame["type"] == "error"
        assert frame["code"] == "update_not_authorised"

    def test_update_past_deadline_returns_error(self):
        msg_db = _messaging_db()
        msg_db.scalar.return_value = _mock_bmq(past_deadline=True)

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame())
                    frame = json.loads(ws.receive_text())

        assert frame["type"] == "error"
        assert frame["code"] == "edit_deadline_passed"

    def test_update_offline_recipient_queues_new_delivery(self):
        existing = _mock_bmq()
        msg_db = _messaging_db()
        msg_db.scalar.return_value = existing

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame(ciphertext="updated_ct"))

        assert existing.ciphertext == "updated_ct"
        added = [type(c.args[0]).__name__ for c in msg_db.add.call_args_list]
        assert "TTLDeliveryQueue" in added
        msg_db.commit.assert_called()

    def test_update_online_recipient_delivered(self):
        bob_ws = AsyncMock()
        existing = _mock_bmq()
        msg_db = _messaging_db()
        msg_db.scalar.return_value = existing

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with patch.object(_app.state.sessions, "get", return_value=bob_ws):
                    with _client.websocket_connect("/ws") as ws:
                        ws.send_text(_login_frame())
                        ws.send_text(self._frame(ciphertext="updated_ct"))

        assert existing.ciphertext == "updated_ct"
        bob_ws.send_text.assert_awaited_once()
        delivered = json.loads(bob_ws.send_text.call_args[0][0])
        assert delivered["type"] == "deliver_message"
        assert delivered["ciphertext"] == "updated_ct"


class TestMidValidation:
    def _frame(self, mid, recipient="bob"):
        return json.dumps(
            {"type": "send_message", "recipient": recipient, "ciphertext": "ct", "mid": mid}
        )

    def test_invalid_format_returns_error(self):
        msg_db = _messaging_db()
        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame(mid="not-a-valid-mid"))
                    frame = json.loads(ws.receive_text())
        assert frame["type"] == "error"
        assert frame["code"] == "invalid_mid"

    def test_sender_mismatch_returns_error(self):
        msg_db = _messaging_db()
        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame(mid=_valid_mid(sender="carol")))
                    frame = json.loads(ws.receive_text())
        assert frame["type"] == "error"
        assert frame["code"] == "invalid_mid"

    def test_recipient_mismatch_returns_error(self):
        msg_db = _messaging_db()
        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame(mid=_valid_mid(recipient="carol"), recipient="bob"))
                    frame = json.loads(ws.receive_text())
        assert frame["type"] == "error"
        assert frame["code"] == "invalid_mid"

    def test_stale_timestamp_returns_edit_deadline_passed(self):
        msg_db = _messaging_db()
        stale_ts = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp() * 1000)
        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame(mid=f"alice:bob:{stale_ts}"))
                    frame = json.loads(ws.receive_text())
        assert frame["type"] == "error"
        assert frame["code"] == "edit_deadline_passed"

    def test_future_timestamp_returns_error(self):
        msg_db = _messaging_db()
        future_ts = int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp() * 1000)
        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame(mid=f"alice:bob:{future_ts}"))
                    frame = json.loads(ws.receive_text())
        assert frame["type"] == "error"
        assert frame["code"] == "invalid_mid"


class TestPublishKeyBundle:
    def _frame(self, otpks=None):
        return json.dumps(
            {
                "type": "publish_key_bundle",
                "identity_key": "ik_base64",
                "signed_pre_key": "spk_base64",
                "signed_pre_key_sig": "sig_base64",
                "one_time_pre_keys": otpks if otpks is not None else ["otpk1", "otpk2", "otpk3"],
            }
        )

    def test_new_bundle_is_inserted(self):
        kbd_db = MagicMock()
        kbd_db.scalar.return_value = None
        msg_db = _messaging_db()

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with patch(_KBD_SL, return_value=_session_cm(kbd_db)):
                    with _client.websocket_connect("/ws") as ws:
                        ws.send_text(_login_frame())
                        ws.send_text(self._frame())

        added = [type(c.args[0]).__name__ for c in kbd_db.add.call_args_list]
        assert "KeyBundle" in added
        assert added.count("OneTimePreKey") == 3
        kbd_db.commit.assert_called_once()

    def test_existing_bundle_is_updated(self):
        existing = MagicMock(spec=KeyBundle)
        kbd_db = MagicMock()
        kbd_db.scalar.return_value = existing
        msg_db = _messaging_db()

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with patch(_KBD_SL, return_value=_session_cm(kbd_db)):
                    with _client.websocket_connect("/ws") as ws:
                        ws.send_text(_login_frame())
                        ws.send_text(self._frame())

        assert existing.identity_key == "ik_base64"
        assert existing.signed_pre_key == "spk_base64"
        assert existing.signed_pre_key_sig == "sig_base64"

    def test_empty_otpk_list_rejected(self):
        msg_db = _messaging_db()

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame(otpks=[]))
                    frame = json.loads(ws.receive_text())

        assert frame["type"] == "error"
        assert frame["code"] == "invalid_frame"

    def test_empty_string_otpk_rejected(self):
        msg_db = _messaging_db()

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with _client.websocket_connect("/ws") as ws:
                    ws.send_text(_login_frame())
                    ws.send_text(self._frame(otpks=[""]))
                    frame = json.loads(ws.receive_text())

        assert frame["type"] == "error"
        assert frame["code"] == "invalid_frame"


class TestRequestKeyBundle:
    def _frame(self, target="bob"):
        return json.dumps({"type": "request_key_bundle", "target_username": target})

    def test_bundle_served_with_otpk(self):
        bundle = _mock_bundle()
        otpk = _mock_otpk()
        kbd_db = MagicMock()
        kbd_db.scalar.side_effect = [bundle, otpk]
        msg_db = _messaging_db()

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with patch(_KBD_SL, return_value=_session_cm(kbd_db)):
                    with _client.websocket_connect("/ws") as ws:
                        ws.send_text(_login_frame())
                        ws.send_text(self._frame())
                        frame = json.loads(ws.receive_text())

        assert frame["type"] == "key_bundle_response"
        assert frame["username"] == "bob"
        assert frame["identity_key"] == "ik_base64"
        assert frame["one_time_pre_key"] == "otpk_base64"
        kbd_db.delete.assert_called_once_with(otpk)
        kbd_db.commit.assert_called_once()

    def test_bundle_served_without_otpk_when_pool_exhausted(self):
        bundle = _mock_bundle()
        kbd_db = MagicMock()
        kbd_db.scalar.side_effect = [bundle, None]
        msg_db = _messaging_db()

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with patch(_KBD_SL, return_value=_session_cm(kbd_db)):
                    with _client.websocket_connect("/ws") as ws:
                        ws.send_text(_login_frame())
                        ws.send_text(self._frame())
                        frame = json.loads(ws.receive_text())

        assert frame["type"] == "key_bundle_response"
        assert frame["one_time_pre_key"] is None
        kbd_db.delete.assert_not_called()

    def test_missing_bundle_returns_error(self):
        kbd_db = MagicMock()
        kbd_db.scalar.return_value = None
        msg_db = _messaging_db()

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with patch(_KBD_SL, return_value=_session_cm(kbd_db)):
                    with _client.websocket_connect("/ws") as ws:
                        ws.send_text(_login_frame())
                        ws.send_text(self._frame())
                        frame = json.loads(ws.receive_text())

        assert frame["type"] == "error"
        assert frame["code"] == "no_key_bundle"
