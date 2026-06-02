import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ..blockchain.batcher import add_to_blockchain
from ..config.config import config
from ..database.db import SessionLocal
from ..database.models import BlockchainMessageQueue

logger = logging.getLogger(__name__)


def _run_batch() -> int:
    grace = timedelta(seconds=config.messaging.edit_grace_seconds)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - grace

    with SessionLocal() as db:
        rows = (
            db.query(BlockchainMessageQueue)
            .filter(BlockchainMessageQueue.edit_deadline < cutoff)
            .order_by(BlockchainMessageQueue.created_at)
            .all()
        )
        if not rows:
            return 0
        row_ids = [r.id for r in rows]
        messages = [f"{r.mid}:{r.ciphertext}" for r in rows]
    # Connection returned to pool before the blocking network call.

    # Raises on network error or on-chain revert — rows are only deleted on success.
    results = add_to_blockchain(messages)

    with SessionLocal() as db:
        db.query(BlockchainMessageQueue).filter(BlockchainMessageQueue.id.in_(row_ids)).delete(
            synchronize_session=False
        )
        db.commit()

    return len(row_ids)


async def loop() -> None:
    interval = config.blockchain.batch_interval_minutes * 60
    logger.info("Batcher loop running — interval=%ds", interval)

    while True:
        try:
            count = await asyncio.to_thread(_run_batch)
            if count:
                logger.info("Batcher committed %d message(s) to blockchain", count)
            else:
                logger.debug("Batcher: no eligible messages this cycle")
        except Exception:
            logger.exception("Batcher run failed — will retry after interval")
        await asyncio.sleep(interval)
