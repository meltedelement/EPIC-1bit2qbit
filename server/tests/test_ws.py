import json
from unittest.mock import MagicMock, patch

import pytest
from argon2 import PasswordHasher
from backend.auth.credentials import verify_credentials
from backend.crypto.password import hash_password
from backend.routes.ws import router
from backend.session import SessionRegistry
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

_app = FastAPI()
_app.state.sessions = SessionRegistry()
_app.include_router(router)
_client = TestClient(_app)

_PASSWORD = "correct-horse-battery-staple"
_HASHED = hash_password(_PASSWORD)


def _mock_db(user=None):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


def _mock_user():
    user = MagicMock()
    user.password_hash = _HASHED
    return user


def _login_frame(username="alice", password=_PASSWORD):
    return json.dumps({"username": username, "password": password})


class TestVerifyCredentials:
    def test_valid_credentials_returns_true(self):
        with patch("backend.auth.credentials.SessionLocal", return_value=_mock_db(_mock_user())):
            assert verify_credentials("alice", _PASSWORD) is True

    def test_wrong_password_returns_false(self):
        with patch("backend.auth.credentials.SessionLocal", return_value=_mock_db(_mock_user())):
            assert verify_credentials("alice", "wrong-password") is False

    def test_unknown_username_returns_false(self):
        with patch("backend.auth.credentials.SessionLocal", return_value=_mock_db(user=None)):
            assert verify_credentials("unknown", _PASSWORD) is False

    def test_outdated_hash_is_rehashed_on_login(self):
        old_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(_PASSWORD)
        user = MagicMock()
        user.password_hash = old_hash
        mock_db = _mock_db(user)
        with patch("backend.auth.credentials.SessionLocal", return_value=mock_db):
            assert verify_credentials("alice", _PASSWORD) is True
        assert user.password_hash != old_hash
        mock_db.commit.assert_called_once()

    def test_outdated_hash_not_rehashed_on_wrong_password(self):
        old_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(_PASSWORD)
        user = MagicMock()
        user.password_hash = old_hash
        mock_db = _mock_db(user)
        with patch("backend.auth.credentials.SessionLocal", return_value=mock_db):
            assert verify_credentials("alice", "wrong-password") is False
        assert user.password_hash == old_hash
        mock_db.commit.assert_not_called()


class TestWebSocketAuth:
    def test_valid_login_accepted(self):
        with patch("backend.auth.credentials.SessionLocal", return_value=_mock_db(_mock_user())):
            with _client.websocket_connect("/ws") as ws:
                ws.send_text(_login_frame())
                ws.send_text("hello")

    def test_invalid_json_closes_4000(self):
        with _client.websocket_connect("/ws") as ws:
            ws.send_text("not json")
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_text()
        assert exc.value.code == 4000

    def test_missing_fields_closes_4000(self):
        with _client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"username": "alice"}))
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_text()
        assert exc.value.code == 4000

    def test_wrong_password_closes_4001(self):
        with patch("backend.auth.credentials.SessionLocal", return_value=_mock_db(_mock_user())):
            with _client.websocket_connect("/ws") as ws:
                ws.send_text(_login_frame(password="wrong-password"))
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_text()
        assert exc.value.code == 4001

    def test_unknown_user_closes_4001(self):
        with patch("backend.auth.credentials.SessionLocal", return_value=_mock_db(user=None)):
            with _client.websocket_connect("/ws") as ws:
                ws.send_text(_login_frame())
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_text()
        assert exc.value.code == 4001

    def test_duplicate_session_closes_4002(self):
        with patch("backend.auth.credentials.SessionLocal", return_value=_mock_db(_mock_user())):
            with _client.websocket_connect("/ws") as first:
                first.send_text(_login_frame())
                with _client.websocket_connect("/ws") as second:
                    second.send_text(_login_frame())
                    with pytest.raises(WebSocketDisconnect) as exc:
                        second.receive_text()
                assert exc.value.code == 4002


class TestWebSocketMessages:
    def test_oversized_message_closes_1009(self):
        with patch("backend.auth.credentials.SessionLocal", return_value=_mock_db(_mock_user())):
            with _client.websocket_connect("/ws") as ws:
                ws.send_text(_login_frame())
                ws.send_text("x" * 4097)
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_text()
        assert exc.value.code == 1009

    def test_message_at_limit_accepted(self):
        with patch("backend.auth.credentials.SessionLocal", return_value=_mock_db(_mock_user())):
            with _client.websocket_connect("/ws") as ws:
                ws.send_text(_login_frame())
                ws.send_text("x" * 4096)
