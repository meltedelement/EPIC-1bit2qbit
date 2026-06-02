import json
from unittest.mock import MagicMock, patch

import pytest
from backend.database.db import get_db
from backend.rate_limit import RateLimiter, client_ip
from backend.routes.auth import router as auth_router
from backend.routes.ws import router as ws_router
from backend.session import SessionRegistry
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

_AUTH_CFG = "backend.routes.auth.config"
_WS_CFG = "backend.routes.ws.config"


class TestClientIp:
    def test_returns_x_real_ip_when_present(self):
        headers = {"x-real-ip": "1.2.3.4"}
        assert client_ip(headers, None) == "1.2.3.4"

    def test_falls_back_to_socket_address_with_warning(self):
        socket = MagicMock()
        socket.host = "127.0.0.1"
        with patch("backend.rate_limit.logger") as mock_log:
            result = client_ip({}, socket)
        assert result == "127.0.0.1"
        mock_log.warning.assert_called_once()

    def test_x_real_ip_takes_priority_over_socket_address(self):
        headers = {"x-real-ip": "5.6.7.8"}
        socket = MagicMock()
        socket.host = "127.0.0.1"
        assert client_ip(headers, socket) == "5.6.7.8"


class TestRateLimiterHit:
    def test_allows_requests_under_limit(self):
        rl = RateLimiter(max_window_seconds=900)
        for _ in range(5):
            assert rl.hit("ip", 5, 60) == 0

    def test_blocks_when_limit_reached(self):
        rl = RateLimiter(max_window_seconds=900)
        for _ in range(5):
            rl.hit("ip", 5, 60)
        assert rl.hit("ip", 5, 60) > 0

    def test_retry_after_is_at_least_one(self):
        rl = RateLimiter(max_window_seconds=900)
        for _ in range(3):
            rl.hit("ip", 3, 60)
        assert rl.hit("ip", 3, 60) >= 1

    def test_different_keys_are_independent(self):
        rl = RateLimiter(max_window_seconds=900)
        for _ in range(3):
            rl.hit("blocked-ip", 3, 60)
        rl.hit("blocked-ip", 3, 60)  # now blocked
        assert rl.hit("other-ip", 3, 60) == 0

    def test_expired_hits_are_pruned(self):
        rl = RateLimiter(max_window_seconds=900)
        t = 1000.0
        with patch("backend.rate_limit.time.monotonic", return_value=t):
            for _ in range(3):
                rl.hit("ip", 3, 60)
        with patch("backend.rate_limit.time.monotonic", return_value=t + 61.0):
            assert rl.hit("ip", 3, 60) == 0

    def test_expired_key_is_removed_from_map(self):
        rl = RateLimiter(max_window_seconds=900)
        t = 1000.0
        with patch("backend.rate_limit.time.monotonic", return_value=t):
            rl.hit("ip", 5, 60)
        with patch("backend.rate_limit.time.monotonic", return_value=t + 901.0):
            rl.sweep()  # max_window=900, so entry is now stale
        assert len(rl) == 0


class TestRateLimiterIsBlocked:
    def test_returns_zero_when_under_limit(self):
        rl = RateLimiter(max_window_seconds=900)
        assert rl.is_blocked("ip", 5, 60) == 0

    def test_returns_retry_after_when_blocked(self):
        rl = RateLimiter(max_window_seconds=900)
        for _ in range(5):
            rl.hit("ip", 5, 60)
        assert rl.is_blocked("ip", 5, 60) >= 1

    def test_does_not_record_a_hit(self):
        rl = RateLimiter(max_window_seconds=900)
        limit = 3
        for _ in range(10):
            rl.is_blocked("ip", limit, 60)
        assert rl.hit("ip", limit, 60) == 0


class TestRegisterRateLimit:
    _LIMIT = 3

    def _make_app(self) -> tuple[FastAPI, TestClient]:
        app = FastAPI()
        app.state.rate_limiter = RateLimiter(max_window_seconds=900)
        def _db():
            return MagicMock()
        app.dependency_overrides[get_db] = _db
        app.include_router(auth_router)
        return app, TestClient(app)

    def _mock_cfg(self):
        cfg = MagicMock()
        cfg.rate_limiting.register_limit = self._LIMIT
        cfg.rate_limiting.register_window_seconds = 60
        return cfg

    def test_allows_requests_under_limit(self):
        _, client = self._make_app()
        with patch(_AUTH_CFG, self._mock_cfg()):
            with patch("backend.routes.auth.hash_password", return_value="hashed"):
                for i in range(self._LIMIT):
                    r = client.post("/register", json={"username": f"user{i}", "password": "pass"})
                    assert r.status_code == 201

    def test_blocks_on_exceeding_limit(self):
        _, client = self._make_app()
        with patch(_AUTH_CFG, self._mock_cfg()):
            with patch("backend.routes.auth.hash_password", return_value="hashed"):
                for i in range(self._LIMIT):
                    client.post("/register", json={"username": f"user{i}", "password": "pass"})
                r = client.post("/register", json={"username": "overflow", "password": "pass"})
        assert r.status_code == 429

    def test_429_includes_retry_after_header(self):
        _, client = self._make_app()
        with patch(_AUTH_CFG, self._mock_cfg()):
            with patch("backend.routes.auth.hash_password", return_value="hashed"):
                for i in range(self._LIMIT + 1):
                    r = client.post("/register", json={"username": f"user{i}", "password": "pass"})
        assert "Retry-After" in r.headers
        assert int(r.headers["Retry-After"]) >= 1


class TestWsAuthRateLimit:
    _LIMIT = 3

    def _make_app(self) -> tuple[FastAPI, TestClient]:
        app = FastAPI()
        app.state.sessions = SessionRegistry()
        app.state.rate_limiter = RateLimiter(max_window_seconds=900)
        app.include_router(ws_router)
        return app, TestClient(app)

    def _mock_cfg(self):
        cfg = MagicMock()
        cfg.rate_limiting.ws_auth_fail_limit = self._LIMIT
        cfg.rate_limiting.ws_auth_fail_window_seconds = 60
        return cfg

    def _no_user_db(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    def test_blocks_after_repeated_failed_logins(self):
        _, client = self._make_app()
        with patch(_WS_CFG, self._mock_cfg()):
            with patch("backend.auth.credentials.SessionLocal", return_value=self._no_user_db()):
                for _ in range(self._LIMIT):
                    with client.websocket_connect("/ws") as ws:
                        ws.send_text(json.dumps({"username": "alice", "password": "wrong"}))
                        with pytest.raises(WebSocketDisconnect) as exc:
                            ws.receive_text()
                    assert exc.value.code == 4001

                with client.websocket_connect("/ws") as ws:
                    with pytest.raises(WebSocketDisconnect) as exc:
                        ws.receive_text()
                assert exc.value.code == 4004

    def test_blocked_ip_closes_before_reading_frame(self):
        """Server closes 4004 before receiving any frame when IP is already blocked."""
        app, client = self._make_app()
        limiter: RateLimiter = app.state.rate_limiter
        for _ in range(self._LIMIT):
            limiter.hit("testclient", self._LIMIT, 60)

        with patch(_WS_CFG, self._mock_cfg()):
            with client.websocket_connect("/ws") as ws:
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_text()  # no send_text — server must close without reading
        assert exc.value.code == 4004
