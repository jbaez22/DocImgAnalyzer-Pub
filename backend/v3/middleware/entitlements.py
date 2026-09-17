"""Entitlement enforcement — scan limits and feature gating by subscription tier."""

from fastapi import HTTPException, status

from ..db import dynamodb as db

_SCAN_LIMITS = {"free": 10, "pro": 200, "enterprise": None}
_IMAGE_SCAN_TIERS = {"pro", "enterprise"}
_ORG_TIERS = {"enterprise"}


def check_scan_quota(user_id: str) -> dict:
    """Raise 429 if the user has exhausted their monthly scan quota.

    Returns the subscription record so callers can avoid a second lookup.
    """
    sub = db.get_subscription(user_id)
    limit = _SCAN_LIMITS.get(sub.get("tier", "free"))
    if limit is not None and sub.get("scan_count_month", 0) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Monthly scan limit of {limit} reached. "
                "Upgrade your plan at /api/v3/billing/checkout."
            ),
        )
    return sub


def require_image_scan(user_id: str) -> None:
    """Raise 403 if the user's tier does not include image scanning."""
    sub = db.get_subscription(user_id)
    if sub.get("tier", "free") not in _IMAGE_SCAN_TIERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Image scanning is available on Pro and Enterprise plans.",
        )


def require_org_feature(user_id: str) -> None:
    """Raise 403 if the user's tier does not include org accounts."""
    sub = db.get_subscription(user_id)
    if sub.get("tier", "free") not in _ORG_TIERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization accounts are available on the Enterprise plan.",
        )
