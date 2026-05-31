from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..auth.credentials import verify_credentials
from ..database.schemas import LoginFrame

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ws"])

_MAX_MESSAGE_LEN = 4096
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


async def _authenticate(websocket: WebSocket) -> str | None:
    """Read first frame and return username on success, or close and return None."""
    try:
        raw = await websocket.receive_text()
    except WebSocketDisconnect:
        return None

    try:
        frame = LoginFrame.model_validate_json(raw)
    except ValidationError:
        await websocket.close(code=4000, reason="invalid login frame")
        return None

    ok = await asyncio.to_thread(verify_credentials, frame.username, frame.password)
    if not ok:
        await websocket.close(code=4001, reason="authentication failed")
        return None

    return frame.username


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    username = await _authenticate(websocket)
    if username is None:
        return

    logger.info("session opened: user=%s", repr(username))

    try:
        while True:
            message = await websocket.receive_text()
            if len(message) > _MAX_MESSAGE_LEN:
                await websocket.close(code=1009, reason="message too large")
                return
            safe = _CONTROL_CHARS.sub("", message)
            logger.info("message from '%s': %s", username, safe)
    except WebSocketDisconnect:
        logger.info("session closed: user=%s", repr(username))
