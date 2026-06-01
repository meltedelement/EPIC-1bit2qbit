from fastapi import WebSocket


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, WebSocket] = {}

    def register(self, username: str, ws: WebSocket) -> bool:
        """Add session. Returns False (without registering) if user is already connected."""
        if username in self._sessions:
            return False
        self._sessions[username] = ws
        return True

    def unregister(self, username: str) -> None:
        self._sessions.pop(username, None)

    def get(self, username: str) -> WebSocket | None:
        return self._sessions.get(username)

    def is_online(self, username: str) -> bool:
        return username in self._sessions
