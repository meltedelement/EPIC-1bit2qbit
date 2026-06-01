import logging
from datetime import datetime, timezone

from sqlalchemy import select

from ..database.db import SessionLocal
from ..database.models import KeyBundle, OneTimePreKey
from ..schemas.ws import (
    ErrorFrame,
    KeyBundleResponseFrame,
    PublishKeyBundleFrame,
    RequestKeyBundleFrame,
)
from . import WsContext

logger = logging.getLogger(__name__)


async def handle_publish_key_bundle(frame: PublishKeyBundleFrame, ctx: WsContext) -> None:
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        existing = db.scalar(select(KeyBundle).where(KeyBundle.owner_username == ctx.username))
        if existing is not None:
            existing.identity_key = frame.identity_key
            existing.signed_pre_key = frame.signed_pre_key
            existing.signed_pre_key_sig = frame.signed_pre_key_sig
            existing.published_at = now
        else:
            db.add(
                KeyBundle(
                    owner_username=ctx.username,
                    identity_key=frame.identity_key,
                    signed_pre_key=frame.signed_pre_key,
                    signed_pre_key_sig=frame.signed_pre_key_sig,
                    published_at=now,
                )
            )

        for key_data in frame.one_time_pre_keys:
            db.add(
                OneTimePreKey(
                    owner_username=ctx.username,
                    key_data=key_data,
                    created_at=now,
                )
            )

        db.commit()

    action = "updated" if existing is not None else "created"
    logger.info("key bundle %s: user=%r otpks=%d", action, ctx.username, len(frame.one_time_pre_keys))


async def handle_request_key_bundle(frame: RequestKeyBundleFrame, ctx: WsContext) -> None:
    error: str | None = None
    response: KeyBundleResponseFrame | None = None

    with SessionLocal() as db:
        bundle = db.scalar(
            select(KeyBundle).where(KeyBundle.owner_username == frame.target_username)
        )

        if bundle is None:
            error = f"no key bundle found for {frame.target_username!r}"
        else:
            otpk = db.scalar(
                select(OneTimePreKey)
                .where(OneTimePreKey.owner_username == frame.target_username)
                .limit(1)
                .with_for_update()
            )

            otpk_data: str | None = None
            if otpk is not None:
                otpk_data = otpk.key_data
                db.delete(otpk)

            db.commit()

            response = KeyBundleResponseFrame(
                username=frame.target_username,
                identity_key=bundle.identity_key,
                signed_pre_key=bundle.signed_pre_key,
                signed_pre_key_sig=bundle.signed_pre_key_sig,
                one_time_pre_key=otpk_data,
            )

    if error is not None:
        logger.warning("key bundle request failed: requester=%r target=%r reason=%s", ctx.username, frame.target_username, error)
        await ctx.websocket.send_text(
            ErrorFrame(code="no_key_bundle", detail=error).model_dump_json()
        )
        return

    logger.debug(
        "key bundle served: requester=%r target=%r otpk=%s",
        ctx.username,
        frame.target_username,
        "yes" if response.one_time_pre_key else "no (pool exhausted)",
    )
    await ctx.websocket.send_text(response.model_dump_json())
