"""API key creation and management for API v3."""

import hashlib
import secrets
from datetime import datetime, timezone

from ..db import dynamodb as db

_PREFIX = "dia_"
_MAX_KEYS_PER_USER = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_api_key(user_id: str, name: str) -> dict:
    """Generate a new API key. Returns the raw key — shown once."""
    existing = db.list_api_keys(user_id)
    active = [k for k in existing if not k.get("revoked")]
    if len(active) >= _MAX_KEYS_PER_USER:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum of {_MAX_KEYS_PER_USER} active API keys allowed.",
        )

    raw = _PREFIX + secrets.token_hex(32)
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    key_id = secrets.token_hex(16)

    db.put_api_key(
        {
            "key_id": key_id,
            "user_id": user_id,
            "name": name,
            "key_hash": key_hash,
            "created_at": _now(),
            "last_used_at": None,
            "revoked": False,
        }
    )

    return {
        "key_id": key_id,
        "name": name,
        "raw_key": raw,
        "created_at": _now(),
    }


def list_api_keys(user_id: str) -> list[dict]:
    return db.list_api_keys(user_id)


def revoke_api_key(user_id: str, key_id: str) -> None:
    record = db.get_api_key(key_id)
    if not record:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Key not found"
        )
    if record["user_id"] != user_id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    db.revoke_api_key(key_id)
