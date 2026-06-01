import logging
from datetime import datetime, timedelta, timezone

from fastapi import WebSocket
from sqlalchemy import delete, select

from ..config.config import config
from ..database.db import SessionLocal
from ..database.models import BlockchainMessageQueue, TTLDeliveryQueue, User
from ..schemas.ws import DeliverMessageFrame, ErrorFrame, SendMessageFrame
from . import WsContext

logger = logging.getLogger(__name__)

def _validate_mid(mid: str, sender: str, recipient: str, now: datetime) -> ErrorFrame | None:
    try:
        parts = mid.split(":")
        if len(parts) != 3:
            raise ValueError
        mid_sender, mid_recipient, ts_str = parts
        mid_ts = datetime.fromtimestamp(int(ts_str) / 1000, tz=timezone.utc)
    except Exception:
        return ErrorFrame(code="invalid_mid", detail="mid must be sender:recipient:timestamp_ms")

    if mid_sender != sender:
        return ErrorFrame(code="invalid_mid", detail="mid sender does not match authenticated user")
    if mid_recipient != recipient:
        return ErrorFrame(code="invalid_mid", detail="mid recipient does not match frame recipient")

    edit_window = timedelta(minutes=config.messaging.edit_window_minutes)
    grace = timedelta(seconds=config.messaging.edit_grace_seconds)
    if mid_ts < now - edit_window - grace:
        return ErrorFrame(code="edit_deadline_passed", detail="edit window has closed for this message")
    if mid_ts > now:
        return ErrorFrame(code="invalid_mid", detail="mid timestamp is in the future")

    return None


async def _deliver_or_queue(
    recipient_ws: WebSocket,
    deliver_json: str,
    recipient_username: str,
    now: datetime,
    mid: str,
    sender: str,
) -> None:
    try:
        await recipient_ws.send_text(deliver_json)
        logger.debug("message delivered: mid=%r from=%r to=%r", mid, sender, recipient_username)
    except Exception:
        # Recipient disconnected between registry check and send.
        # Queue the frame so they receive it on reconnect.
        logger.warning("direct delivery to %r failed, queuing offline", recipient_username)
        with SessionLocal() as db:
            expires_at = now + timedelta(days=config.messaging.message_ttl_days)
            db.add(
                TTLDeliveryQueue(
                    recipient_username=recipient_username,
                    frame_json=deliver_json,
                    created_at=now,
                    expires_at=expires_at,
                )
            )
            db.commit()


async def handle_send_message(frame: SendMessageFrame, ctx: WsContext) -> None:
    now = datetime.now(timezone.utc)

    deliver_json = DeliverMessageFrame(
        sender=ctx.username,
        ciphertext=frame.ciphertext,
        mid=frame.mid,
    ).model_dump_json()

    recipient_username: str | None = None
    recipient_ws: WebSocket | None = None
    error_frame: ErrorFrame | None = None

    with SessionLocal() as db:
        existing = db.scalar(
            select(BlockchainMessageQueue).where(BlockchainMessageQueue.mid == frame.mid)
        )

        if existing is not None:
            # mid already staged — treat as a ciphertext update if sender matches
            if existing.sender_username != ctx.username:
                error_frame = ErrorFrame(
                    code="update_not_authorised",
                    detail="update not authorised",
                )
            elif now >= existing.edit_deadline + timedelta(seconds=config.messaging.edit_grace_seconds):
                error_frame = ErrorFrame(
                    code="edit_deadline_passed",
                    detail="edit window has closed for this message",
                )
            else:
                recipient_username = existing.recipient_username
                existing.ciphertext = frame.ciphertext
        else:
            # New message — validate mid structure before hitting the DB
            error_frame = _validate_mid(frame.mid, ctx.username, frame.recipient, now)
            if error_frame is None:
                recipient = db.scalar(select(User).where(User.username == frame.recipient))
                if recipient is None:
                    logger.warning(
                        "send_message rejected: unknown recipient=%r sender=%r",
                        frame.recipient,
                        ctx.username,
                    )
                    error_frame = ErrorFrame(
                        code="unknown_recipient",
                        detail=f"no user with username {frame.recipient!r}",
                    )
                else:
                    recipient_username = frame.recipient
                    edit_deadline = now + timedelta(minutes=config.messaging.edit_window_minutes)
                    db.add(
                        BlockchainMessageQueue(
                            mid=frame.mid,
                            sender_username=ctx.username,
                            recipient_username=recipient_username,
                            ciphertext=frame.ciphertext,
                            created_at=now,
                            edit_deadline=edit_deadline,
                        )
                    )

        if error_frame is None:
            expires_at = now + timedelta(days=config.messaging.message_ttl_days)
            recipient_ws = ctx.registry.get(recipient_username)
            if recipient_ws is None:
                db.add(
                    TTLDeliveryQueue(
                        recipient_username=recipient_username,
                        frame_json=deliver_json,
                        created_at=now,
                        expires_at=expires_at,
                    )
                )
                logger.debug(
                    "message queued offline: mid=%r from=%r to=%r",
                    frame.mid,
                    ctx.username,
                    recipient_username,
                )
            db.commit()

    if error_frame is not None:
        await ctx.websocket.send_text(error_frame.model_dump_json())
        return

    if recipient_ws is not None:
        await _deliver_or_queue(recipient_ws, deliver_json, recipient_username, now, frame.mid, ctx.username) 


async def drain_offline_queue(ctx: WsContext) -> None:
    with SessionLocal() as db:
        rows = db.scalars(
            select(TTLDeliveryQueue)
            .where(TTLDeliveryQueue.recipient_username == ctx.username)
            .order_by(TTLDeliveryQueue.created_at)
        ).all()
        frames = [(row.id, DeliverMessageFrame.model_validate_json(row.frame_json)) for row in rows]

    if not frames:
        return

    logger.info("draining offline queue: user=%r count=%d", ctx.username, len(frames))
    for row_id, deliver in frames:
        await ctx.websocket.send_text(deliver.model_dump_json())
        logger.debug(
            "message delivered: mid=%r from=%r to=%r", deliver.mid, deliver.sender, ctx.username
        )
        with SessionLocal() as db:
            db.execute(delete(TTLDeliveryQueue).where(TTLDeliveryQueue.id == row_id))
            db.commit()
    logger.debug("offline queue drained: user=%r", ctx.username)
