from dataclasses import dataclass

from fastapi import WebSocket

from ..session import SessionRegistry


@dataclass
class WsContext:
    username: str
    websocket: WebSocket
    registry: SessionRegistry
