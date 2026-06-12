"""
Xenia CRM – Campaign Dispatch Service
Handles the sending of campaign messages to the Channel Simulation Service (Service B).

Architecture:
- Current implementation: FastAPI BackgroundTasks (zero dependencies, works immediately)
- Future migration path: Replace _enqueue_batch() with RQ or Celery task — zero other changes needed
- Designed for 50k+ recipients via batched sends

Responsibilities:
- Batch outbound messages into configurable chunk sizes
- Send each batch to Service B asynchronously
- Retry failed sends with exponential backoff
- Mark communications as 'sent' or 'failed' after dispatch
- Log all retry attempts for observability
"""

import logging
import time
import httpx
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session

from app.models.campaign import Communication
from app.config import settings

logger = logging.getLogger("xenia.dispatch")

# ── Configuration ─────────────────────────────────────────────────────────────
CHANNEL_SERVICE_SEND_URL = f"{settings.channel_service_url}/send"
BATCH_SIZE = 100          # messages per HTTP request to Service B
MAX_RETRIES = 3           # max retry attempts per batch
RETRY_BACKOFF_BASE = 2.0  # exponential backoff: 2s, 4s, 8s


# ── Queue Interface (BackgroundTasks implementation) ──────────────────────────
# To migrate to Redis/RQ:
#   1. Import RQ Queue
#   2. Replace _dispatch_batch_sync() call with q.enqueue(_dispatch_batch_sync, ...)
#   3. No other code changes required
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_campaign_messages(
    db: Session,
    campaign_id: str,
    messages: list[dict[str, Any]]
) -> None:
    """
    Main dispatch entry point — called as a BackgroundTask.
    Splits messages into batches and sends each to Service B with retry logic.

    Args:
        db: SQLAlchemy session
        campaign_id: UUID string of the campaign
        messages: list of {communication_id, customer_id, channel, message}
    """
    total = len(messages)
    logger.info(f"Dispatch started: campaign={campaign_id} total_messages={total}")

    batches = [messages[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    sent_count = 0
    failed_count = 0

    for batch_idx, batch in enumerate(batches):
        comm_ids = [m["communication_id"] for m in batch]

        success = _dispatch_batch_with_retry(campaign_id, batch, batch_idx)

        if success:
            sent_count += len(batch)
            _mark_communications_sent(db, comm_ids)
        else:
            failed_count += len(batch)
            _mark_communications_failed(db, comm_ids)

    logger.info(
        f"Dispatch complete: campaign={campaign_id} "
        f"sent={sent_count} failed={failed_count} total={total}"
    )


def _dispatch_batch_with_retry(
    campaign_id: str,
    batch: list[dict],
    batch_idx: int
) -> bool:
    """
    Sends one batch to Service B with exponential backoff retry.
    Returns True if successful, False after all retries exhausted.
    """
    payload = {
        "campaign_id": campaign_id,
        "messages": batch
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = httpx.post(
                CHANNEL_SERVICE_SEND_URL,
                json=payload,
                timeout=10.0
            )
            if response.status_code in (200, 202):
                logger.info(
                    f"Batch {batch_idx} dispatched successfully "
                    f"(attempt {attempt}, {len(batch)} messages)"
                )
                return True
            else:
                logger.warning(
                    f"Batch {batch_idx} attempt {attempt}: "
                    f"Service B returned {response.status_code} — {response.text[:200]}"
                )
        except httpx.ConnectError:
            logger.warning(
                f"Batch {batch_idx} attempt {attempt}: "
                f"Cannot connect to Channel Service at {CHANNEL_SERVICE_SEND_URL}. "
                f"Is Service B running?"
            )
        except Exception as e:
            logger.error(f"Batch {batch_idx} attempt {attempt}: Unexpected error — {e}")

        if attempt < MAX_RETRIES:
            wait_secs = RETRY_BACKOFF_BASE ** attempt
            logger.info(f"Batch {batch_idx}: retrying in {wait_secs:.0f}s...")
            time.sleep(wait_secs)

    logger.error(
        f"Batch {batch_idx}: all {MAX_RETRIES} attempts failed. "
        f"Marking {len(batch)} communications as failed."
    )
    return False


def _mark_communications_sent(db: Session, comm_ids: list[str]) -> None:
    """Mark a batch of communications as 'sent' with timestamp."""
    now = datetime.now(timezone.utc)
    db.query(Communication).filter(
        Communication.communication_id.in_(comm_ids)
    ).update(
        {"status": "sent", "sent_at": now},
        synchronize_session=False
    )
    db.commit()


def _mark_communications_failed(db: Session, comm_ids: list[str]) -> None:
    """Mark a batch of communications as 'failed' and increment retry_count."""
    db.query(Communication).filter(
        Communication.communication_id.in_(comm_ids)
    ).update(
        {"status": "failed", "retry_count": Communication.retry_count + 1},
        synchronize_session=False
    )
    db.commit()
