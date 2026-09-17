"""Org account management for Enterprise users."""

import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status

from ..db import dynamodb as db
from ..middleware.entitlements import require_org_feature


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_org(user_id: str, name: str) -> dict:
    require_org_feature(user_id)
    existing = db.get_org_by_admin(user_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already manage an organization.",
        )
    org_id = secrets.token_hex(16)
    item = {
        "org_id": org_id,
        "name": name,
        "admin_user_id": user_id,
        "member_ids": {user_id},
        "created_at": _now(),
    }
    db.put_org(item)
    return {**item, "member_ids": list(item["member_ids"])}


def get_org(user_id: str) -> dict:
    org = db.get_org_by_admin(user_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No organization found"
        )
    return {**org, "member_ids": list(org.get("member_ids", []))}


def add_member(admin_user_id: str, org_id: str, member_user_id: str) -> None:
    org = db.get_org(org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Org not found"
        )
    if org["admin_user_id"] != admin_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    db.add_org_member(org_id, member_user_id)
