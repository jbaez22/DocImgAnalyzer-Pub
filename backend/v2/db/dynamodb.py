"""DynamoDB v2 data access layer.

Table key: scan_id (hash)
GSI: user-scans-index — hash: user_id, range: created_at (newest-first query)
"""

import base64
import json
import os
from decimal import Decimal
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "")

_table = None


def _get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(TABLE_NAME)
    return _table


def _to_python(obj: object) -> object:
    """Convert DynamoDB Decimal types to int/float for JSON serialisation."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _to_python(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_python(i) for i in obj]
    return obj


def get_scan(scan_id: str) -> Optional[dict]:
    """Fetch a single scan record by scan_id. Returns None if not found."""
    response = _get_table().get_item(Key={"scan_id": scan_id})
    item = response.get("Item")
    return _to_python(item) if item else None  # type: ignore[return-value]


def list_user_scans(
    user_id: str,
    limit: int = 20,
    next_token: Optional[str] = None,
) -> dict:
    """Query user-scans-index GSI by user_id, newest first, with cursor pagination."""
    kwargs: dict = {
        "IndexName": "user-scans-index",
        "KeyConditionExpression": Key("user_id").eq(user_id),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if next_token:
        kwargs["ExclusiveStartKey"] = json.loads(base64.b64decode(next_token))

    response = _get_table().query(**kwargs)
    items = [_to_python(item) for item in response.get("Items", [])]

    last_key = response.get("LastEvaluatedKey")
    encoded_token = (
        base64.b64encode(json.dumps(last_key).encode()).decode() if last_key else None
    )
    return {"items": items, "next_token": encoded_token}


def put_scan(item: dict) -> None:
    """Write a scan record (create or overwrite)."""
    _get_table().put_item(Item=item)


def update_scan(scan_id: str, updates: dict) -> None:
    """Partially update attributes on an existing scan record."""
    if not updates:
        return
    update_expr = "SET " + ", ".join(f"#{k} = :{k}" for k in updates)
    expr_names = {f"#{k}": k for k in updates}
    expr_values = {f":{k}": v for k, v in updates.items()}
    _get_table().update_item(
        Key={"scan_id": scan_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )


def delete_scan(scan_id: str) -> None:
    """Delete a scan record by scan_id."""
    _get_table().delete_item(Key={"scan_id": scan_id})


def cancel_scan(scan_id: str) -> None:
    """Set scan status to CANCELLED, only if not already COMPLETE or FAILED."""
    from datetime import datetime, timezone

    _get_table().update_item(
        Key={"scan_id": scan_id},
        UpdateExpression="SET #s = :cancelled, updated_at = :u",
        ConditionExpression="#s IN (:pending, :processing)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":cancelled": "CANCELLED",
            ":pending": "PENDING",
            ":processing": "PROCESSING",
            ":u": datetime.now(timezone.utc).isoformat(),
        },
    )
