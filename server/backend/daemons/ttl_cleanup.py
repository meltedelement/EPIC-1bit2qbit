import asyncio
import logging
from datetime import datetime, timezone

from ..config.config import config
from ..database.db import SessionLocal
from ..database.models import TTLDeliveryQueue

logger = logging.getLogger(__name__)


def _run_cleanup() -> int:
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with SessionLocal() as db:
        count = (
            db.query(TTLDeliveryQueue)
            .filter(TTLDeliveryQueue.expires_at < now)
            .delete(synchronize_session=False)
        )
        db.commit()

    return count


async def loop() -> None:
    interval = config.messaging.ttl_cleanup_interval_hours * 3600
    logger.info("TTL cleanup loop running — interval=%ds", interval)

    while True:
        try:
            count = await asyncio.to_thread(_run_cleanup)
            if count:
                logger.info("TTL cleanup deleted %d expired message(s)", count)
            else:
                logger.debug("TTL cleanup: no expired messages this cycle")
        except Exception:
            logger.exception("TTL cleanup run failed — will retry after interval")
        await asyncio.sleep(interval)
