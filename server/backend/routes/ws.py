from __future__ import annotations

import asyncio
import logging
import re

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
# Pre-hashed dummy used to equalise timing when the username does not exist,
# preventing username enumeration via response-time differences.
_DUMMY_HASH = _ph.hash("dummy")
_MAX_MESSAGE_LEN = 4096
_MAX_LOGIN_FRAME_LEN = 512
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _verify_credentials(username: str, password: str) -> bool:
    """DB lookup + Argon2 verify — runs in a worker thread."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        target_hash = user.password_hash if user is not None else _DUMMY_HASH
        _ph.verify(target_hash, password)
        return user is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    finally:
        db.close()


async def _authenticate(websocket: WebSocket) -> str | None:
    """Read first frame and return username on success, or close and return None."""
    try:
        raw = await websocket.receive_text()
    except WebSocketDisconnect:
        return None

    if len(raw) > _MAX_LOGIN_FRAME_LEN:
        await websocket.close(code=4000, reason="invalid login frame")
        return None

    try:
        frame = LoginFrame.model_validate_json(raw)
    except ValidationError:
        await websocket.close(code=4000, reason="invalid login frame")
        return None

    ok = await asyncio.to_thread(_verify_credentials, frame.username, frame.password)
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
