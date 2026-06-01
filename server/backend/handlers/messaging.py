import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..config.config import config
from ..database.db import SessionLocal
from ..database.models import BlockchainMessageQueue, TTLDeliveryQueue, User
from ..schemas import DeliverMessageFrame, ErrorFrame, SendMessageFrame
from . import WsContext

logger = logging.getLogger(__name__)


async def handle_send_message(frame: SendMessageFrame, ctx: WsContext) -> None:
    now = datetime.now(timezone.utc)
    edit_deadline = now + timedelta(minutes=config.messaging.edit_window_minutes)
    expires_at = now + timedelta(days=config.messaging.message_ttl_days)

    deliver = DeliverMessageFrame(
        sender=ctx.username,
        ciphertext=frame.ciphertext,
        mid=frame.mid,
    )

    with SessionLocal() as db:
        recipient = db.scalar(select(User).where(User.username == frame.recipient))
        if recipient is None:
            await ctx.websocket.send_text(
                ErrorFrame(
                    code="unknown_recipient",
                    detail=f"no user with username {frame.recipient!r}",
                ).model_dump_json()
            )
            return

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
        if recipient_ws is not None:
            await recipient_ws.send_text(deliver.model_dump_json())
        else:
            db.add(
                TTLDeliveryQueue(
                    recipient_username=frame.recipient,
                    frame_json=deliver.model_dump_json(),
                    created_at=now,
                    expires_at=expires_at,
                )
            )

        db.commit()


async def drain_offline_queue(ctx: WsContext) -> None:
    with SessionLocal() as db:
        rows = db.scalars(
            select(TTLDeliveryQueue)
            .where(TTLDeliveryQueue.recipient_username == ctx.username)
            .order_by(TTLDeliveryQueue.created_at)
        ).all()

        for row in rows:
            await ctx.websocket.send_text(row.frame_json)
            db.delete(row)

        db.commit()
