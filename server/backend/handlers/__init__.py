from dataclasses import dataclass

from fastapi import WebSocket

from ..rate_limit import RateLimiter
from ..session import SessionRegistry


@dataclass
class WsContext:
    username: str
    websocket: WebSocket
    registry: SessionRegistry
    kb_limiter: RateLimiter
