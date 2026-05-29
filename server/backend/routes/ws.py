import logging
import re

from __future__ import annotations                                                                                                                        
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..database.db import SessionLocal
from ..database.models import User
from ..database.schemas import LoginFrame

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ws"])

_ph = PasswordHasher()
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

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == frame.username).first()
        if user is None:
            await websocket.close(code=4001, reason="authentication failed")
            return None
        _ph.verify(user.password_hash, frame.password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        await websocket.close(code=4001, reason="authentication failed")
        return None
    finally:
        db.close()

    return frame.username


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    username = await _authenticate(websocket)
    if username is None:
        return

    logger.info("session opened: user='%s'", username)

    try:
        while True:
            message = await websocket.receive_text()
            if len(message) > _MAX_MESSAGE_LEN:
                await websocket.close(code=1009, reason="message too large")
                return
            safe = _CONTROL_CHARS.sub("", message)
            logger.info("message from '%s': %s", username, safe)
    except WebSocketDisconnect:
        logger.info("session closed: user='%s'", username)
