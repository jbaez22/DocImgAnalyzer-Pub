"""Helpers for reading and updating scan status in DynamoDB v2."""

from datetime import datetime, timezone
from typing import Optional

from ..db import dynamodb as db
from ..models.schemas import ScanStatus


def update_status(scan_id: str, status: ScanStatus, **extra_attrs) -> None:
    """Update scan status and timestamp on an existing record."""
    updates = {
        "status": status.value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra_attrs,
    }
    db.update_scan(scan_id, updates)


def get_status(scan_id: str) -> Optional[dict]:
    """Fetch a scan record from DynamoDB v2 by scan_id."""
    return db.get_scan(scan_id)
