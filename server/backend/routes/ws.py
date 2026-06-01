import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from ..auth.credentials import verify_credentials
from ..handlers import WsContext, key_bundle, messaging
from ..schemas.http import LoginFrame
from ..schemas.ws import ErrorFrame, InboundFrame
from ..session import SessionRegistry

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ws"])

_MAX_MESSAGE_LEN = 4096
_MAX_CONSECUTIVE_ERRORS = 5

_frame_adapter: TypeAdapter[InboundFrame] = TypeAdapter(InboundFrame)


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


async def _dispatch(frame: InboundFrame, ctx: WsContext) -> None:
    match frame.type:
        case "send_message":
            await messaging.handle_send_message(frame, ctx)
        case "publish_key_bundle":
            await key_bundle.handle_publish_key_bundle(frame, ctx)
        case "request_key_bundle":
            await key_bundle.handle_request_key_bundle(frame, ctx)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    username = await _authenticate(websocket)
    if username is None:
        return

    registry: SessionRegistry = websocket.app.state.sessions
    if not registry.register(username, websocket):
        await websocket.close(code=4002, reason="already connected")
        return

    logger.info("session opened: user=%s", repr(username))
    ctx = WsContext(username=username, websocket=websocket, registry=registry)

    consecutive_errors = 0
    try:
        await messaging.drain_offline_queue(ctx)
        while True:
            raw = await websocket.receive_text()

            if len(raw) > _MAX_MESSAGE_LEN:
                await websocket.close(code=1009, reason="message too large")
                return

            try:
                frame = _frame_adapter.validate_json(raw)
            except ValidationError as exc:
                consecutive_errors += 1
                logger.warning(
                    "bad frame from %r (%d/%d): %s",
                    username,
                    consecutive_errors,
                    _MAX_CONSECUTIVE_ERRORS,
                    exc,
                )
                if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                    await websocket.close(code=4003, reason="too many invalid frames")
                    return
                await websocket.send_text(
                    ErrorFrame(
                        code="invalid_frame", detail="frame failed validation"
                    ).model_dump_json()
                )
                continue

            consecutive_errors = 0
            await _dispatch(frame, ctx)

    except WebSocketDisconnect:
        logger.info("session closed: user=%s", repr(username))
    finally:
        registry.unregister(username)
