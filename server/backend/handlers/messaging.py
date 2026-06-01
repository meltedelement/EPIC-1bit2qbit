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


async def handle_send_message(frame: SendMessageFrame, ctx: WsContext) -> None:
    now = datetime.now(timezone.utc)
    edit_deadline = now + timedelta(minutes=config.messaging.edit_window_minutes)
    expires_at = now + timedelta(days=config.messaging.message_ttl_days)

    deliver_json = DeliverMessageFrame(
        sender=ctx.username,
        ciphertext=frame.ciphertext,
        mid=frame.mid,
    ).model_dump_json()

    recipient_found = False
    recipient_ws: WebSocket | None = None

    with SessionLocal() as db:
        recipient = db.scalar(select(User).where(User.username == frame.recipient))
        if recipient is not None:
            recipient_found = True
            db.add(
                BlockchainMessageQueue(
                    mid=frame.mid,
                    sender_username=ctx.username,
                    recipient_username=frame.recipient,
                    ciphertext=frame.ciphertext,
                    created_at=now,
                    edit_deadline=edit_deadline,
                )
            )
            recipient_ws = ctx.registry.get(frame.recipient)
            if recipient_ws is None:
                db.add(
                    TTLDeliveryQueue(
                        recipient_username=frame.recipient,
                        frame_json=deliver_json,
                        created_at=now,
                        expires_at=expires_at,
                    )
                )
            db.commit()

    if not recipient_found:
        logger.warning(
            "send_message rejected: unknown recipient=%r sender=%r", frame.recipient, ctx.username
        )
        await ctx.websocket.send_text(
            ErrorFrame(
                code="unknown_recipient",
                detail=f"no user with username {frame.recipient!r}",
            ).model_dump_json()
        )
        return

    if recipient_ws is not None:
        try:
            await recipient_ws.send_text(deliver_json)
            logger.debug(
                "message delivered: mid=%r from=%r to=%r", frame.mid, ctx.username, frame.recipient
            )
        except Exception:
            # Recipient disconnected between registry check and send.
            # Queue the frame so they receive it on reconnect.
            logger.warning("direct delivery to %r failed, queuing offline", frame.recipient)
            with SessionLocal() as db:
                db.add(
                    TTLDeliveryQueue(
                        recipient_username=frame.recipient,
                        frame_json=deliver_json,
                        created_at=now,
                        expires_at=expires_at,
                    )
                )
                db.commit()
    else:
        logger.debug(
            "message queued offline: mid=%r from=%r to=%r", frame.mid, ctx.username, frame.recipient
        )


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
