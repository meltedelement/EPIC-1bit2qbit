import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.database.models import KeyBundle, OneTimePreKey, TTLDeliveryQueue, User
from backend.routes.ws import router
from backend.session import SessionRegistry
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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


def _session_cm(db):
    """Wrap a mock db into a context manager that SessionLocal() can return."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=db)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


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
                    ws.send_text(json.dumps({
                        "type": "send_message",
                        "recipient": "bob",
                        "ciphertext": "ct",
                        "mid": "m1",
                    }))
                    ws.receive_text()  # unknown_recipient error
                    for _ in range(4):
                        ws.send_text("not json")
                        ws.receive_text()
                    # Connection still open — no exception raised


class TestSendMessage:
    def _frame(self, recipient="bob", ciphertext="encrypted", mid="msg-001"):
        return json.dumps({
            "type": "send_message",
            "recipient": recipient,
            "ciphertext": ciphertext,
            "mid": mid,
        })

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
        msg_db.scalar.return_value = MagicMock(spec=User)

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
        msg_db.scalar.return_value = MagicMock(spec=User)

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with patch.object(_app.state.sessions, "get", return_value=bob_ws):
                    with _client.websocket_connect("/ws") as ws:
                        ws.send_text(_login_frame())
                        ws.send_text(self._frame())

        bob_ws.send_text.assert_awaited_once()
        delivered = json.loads(bob_ws.send_text.call_args[0][0])
        assert delivered["type"] == "deliver_message"
        assert delivered["mid"] == "msg-001"
        assert delivered["sender"] == "alice"

    def test_online_delivery_failure_falls_back_to_queue(self):
        bob_ws = AsyncMock()
        bob_ws.send_text.side_effect = Exception("disconnected")
        msg_db = _messaging_db()
        msg_db.scalar.return_value = MagicMock(spec=User)

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
        msg_db.scalar.return_value = MagicMock(spec=User)

        with patch(_VERIFY, return_value=True):
            with patch(_MSG_SL, return_value=_session_cm(msg_db)):
                with patch.object(_app.state.sessions, "get", return_value=bob_ws):
                    with _client.websocket_connect("/ws") as ws:
                        ws.send_text(_login_frame())
                        ws.send_text(self._frame())

        added = [type(c.args[0]).__name__ for c in msg_db.add.call_args_list]
        assert "TTLDeliveryQueue" not in added


class TestPublishKeyBundle:
    def _frame(self, otpks=None):
        return json.dumps({
            "type": "publish_key_bundle",
            "identity_key": "ik_base64",
            "signed_pre_key": "spk_base64",
            "signed_pre_key_sig": "sig_base64",
            "one_time_pre_keys": otpks if otpks is not None else ["otpk1", "otpk2", "otpk3"],
        })

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
