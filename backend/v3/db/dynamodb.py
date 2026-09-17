"""DynamoDB data access layer for API v3.

Tables owned by Phase 3:
  - img-analyzer-{env}-subscriptions  (hash: user_id)
  - img-analyzer-{env}-api-keys       (hash: key_id, GSI: user-keys-index)
  - img-analyzer-{env}-orgs           (hash: org_id, GSI: admin-org-index)

Phase 2 table (read-only):
  - img-analyzer-{env}-scans-v2       (hash: scan_id, GSI: user-scans-index)
"""

import base64
import hashlib
import json
import os
from decimal import Decimal
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key

SUBSCRIPTIONS_TABLE = os.environ.get("SUBSCRIPTIONS_TABLE", "")
API_KEYS_TABLE = os.environ.get("API_KEYS_TABLE", "")
ORGS_TABLE = os.environ.get("ORGS_TABLE", "")
SCANS_V2_TABLE = os.environ.get("DYNAMODB_V2_TABLE", "")

_ddb = None


def _resource():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    return _ddb


def _table(name: str):
    return _resource().Table(name)


def _to_python(obj: object) -> object:
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _to_python(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_python(i) for i in obj]
    return obj


# ── Subscriptions ─────────────────────────────────────────────────────────────

_FREE_DEFAULTS = {
    "tier": "free",
    "scan_count_month": 0,
    "scan_limit": 10,
    "period_end": None,
    "payment_past_due": False,
    "stripe_customer_id": None,
    "stripe_subscription_id": None,
}


def get_subscription(user_id: str) -> dict:
    """Return subscription record. Returns free-tier defaults for new users."""
    item = _table(SUBSCRIPTIONS_TABLE).get_item(Key={"user_id": user_id}).get("Item")
    if not item:
        return {"user_id": user_id, **_FREE_DEFAULTS}
    return _to_python(item)  # type: ignore[return-value]


def put_subscription(item: dict) -> None:
    _table(SUBSCRIPTIONS_TABLE).put_item(Item=item)


def update_subscription(user_id: str, updates: dict) -> None:
    if not updates:
        return
    expr = "SET " + ", ".join(f"#{k} = :{k}" for k in updates)
    _table(SUBSCRIPTIONS_TABLE).update_item(
        Key={"user_id": user_id},
        UpdateExpression=expr,
        ExpressionAttributeNames={f"#{k}": k for k in updates},
        ExpressionAttributeValues={f":{k}": v for k, v in updates.items()},
    )


def increment_scan_count(user_id: str) -> None:
    _table(SUBSCRIPTIONS_TABLE).update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET scan_count_month = if_not_exists(scan_count_month, :zero) + :one",
        ExpressionAttributeValues={":zero": 0, ":one": 1},
    )


def get_subscription_by_stripe_customer(stripe_customer_id: str) -> Optional[dict]:
    response = _table(SUBSCRIPTIONS_TABLE).query(
        IndexName="stripe-customer-index",
        KeyConditionExpression=Key("stripe_customer_id").eq(stripe_customer_id),
        Limit=1,
    )
    items = response.get("Items", [])
    return _to_python(items[0]) if items else None  # type: ignore[return-value]


def get_rescan_subscriptions() -> list[dict]:
    """Return all Pro/Enterprise subscriptions with rescan enabled."""
    response = _table(SUBSCRIPTIONS_TABLE).scan(
        FilterExpression="tier IN (:pro, :enterprise) AND rescan_subscribed = :t",
        ExpressionAttributeValues={
            ":pro": "pro",
            ":enterprise": "enterprise",
            ":t": True,
        },
    )
    return [_to_python(item) for item in response.get("Items", [])]  # type: ignore[return-value,misc]


# ── API Keys ──────────────────────────────────────────────────────────────────


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def put_api_key(item: dict) -> None:
    _table(API_KEYS_TABLE).put_item(Item=item)


def get_api_key(key_id: str) -> Optional[dict]:
    item = _table(API_KEYS_TABLE).get_item(Key={"key_id": key_id}).get("Item")
    return _to_python(item) if item else None  # type: ignore[return-value]


def list_api_keys(user_id: str) -> list[dict]:
    response = _table(API_KEYS_TABLE).query(
        IndexName="user-keys-index",
        KeyConditionExpression=Key("user_id").eq(user_id),
    )
    return [_to_python(item) for item in response.get("Items", [])]  # type: ignore[return-value,misc]


def revoke_api_key(key_id: str) -> None:
    _table(API_KEYS_TABLE).update_item(
        Key={"key_id": key_id},
        UpdateExpression="SET revoked = :t",
        ExpressionAttributeValues={":t": True},
    )


def validate_api_key(raw_key: str) -> Optional[dict]:
    """Look up a key by its SHA-256 hash via GSI. Returns None if not found or revoked."""
    key_hash = _hash_key(raw_key)
    response = _table(API_KEYS_TABLE).query(
        IndexName="key-hash-index",
        KeyConditionExpression=Key("key_hash").eq(key_hash),
        FilterExpression=Attr("revoked").not_exists() | Attr("revoked").eq(False),
        Limit=1,
    )
    items = response.get("Items", [])
    return _to_python(items[0]) if items else None  # type: ignore[return-value]


def touch_api_key(key_id: str) -> None:
    from datetime import datetime, timezone

    _table(API_KEYS_TABLE).update_item(
        Key={"key_id": key_id},
        UpdateExpression="SET last_used_at = :t",
        ExpressionAttributeValues={":t": datetime.now(timezone.utc).isoformat()},
    )


# ── Orgs ──────────────────────────────────────────────────────────────────────


def put_org(item: dict) -> None:
    _table(ORGS_TABLE).put_item(Item=item)


def get_org(org_id: str) -> Optional[dict]:
    item = _table(ORGS_TABLE).get_item(Key={"org_id": org_id}).get("Item")
    return _to_python(item) if item else None  # type: ignore[return-value]


def get_org_by_admin(admin_user_id: str) -> Optional[dict]:
    response = _table(ORGS_TABLE).query(
        IndexName="admin-org-index",
        KeyConditionExpression=Key("admin_user_id").eq(admin_user_id),
        Limit=1,
    )
    items = response.get("Items", [])
    return _to_python(items[0]) if items else None  # type: ignore[return-value]


def add_org_member(org_id: str, user_id: str) -> None:
    _table(ORGS_TABLE).update_item(
        Key={"org_id": org_id},
        UpdateExpression="ADD member_ids :uid",
        ExpressionAttributeValues={":uid": {user_id}},
    )


# ── Phase 2 scans (read-only) ─────────────────────────────────────────────────


def get_scan(scan_id: str) -> Optional[dict]:
    item = _table(SCANS_V2_TABLE).get_item(Key={"scan_id": scan_id}).get("Item")
    return _to_python(item) if item else None  # type: ignore[return-value]


def list_user_scans(
    user_id: str,
    limit: int = 20,
    next_token: Optional[str] = None,
) -> dict:
    kwargs: dict = {
        "IndexName": "user-scans-index",
        "KeyConditionExpression": Key("user_id").eq(user_id),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if next_token:
        kwargs["ExclusiveStartKey"] = json.loads(base64.b64decode(next_token))
    response = _table(SCANS_V2_TABLE).query(**kwargs)
    items = [_to_python(item) for item in response.get("Items", [])]
    last_key = response.get("LastEvaluatedKey")
    token = (
        base64.b64encode(json.dumps(last_key).encode()).decode() if last_key else None
    )
    return {"items": items, "next_token": token}


def list_image_scans(user_id: str, image_name: str, limit: int = 50) -> list[dict]:
    response = _table(SCANS_V2_TABLE).query(
        IndexName="user-scans-index",
        KeyConditionExpression=Key("user_id").eq(user_id),
        FilterExpression="image_name = :img",
        ExpressionAttributeValues={":img": image_name},
        Limit=limit,
        ScanIndexForward=True,
    )
    return [_to_python(item) for item in response.get("Items", [])]  # type: ignore[return-value,misc]


def put_scan(item: dict) -> None:
    """Write a new scan record to the Phase 2 scans table (shared table for all phases)."""
    _table(SCANS_V2_TABLE).put_item(Item=item)
