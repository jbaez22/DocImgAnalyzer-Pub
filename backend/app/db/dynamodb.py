import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

_table = None


def _get_table():
    global _table
    if _table is None:
        dynamodb = boto3.resource("dynamodb")
        _table = dynamodb.Table(os.environ["DYNAMODB_TABLE_NAME"])
    return _table


def _to_python(obj: object) -> object:
    """Convert DynamoDB Decimal types back to int/float for JSON serialisation."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _to_python(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_python(i) for i in obj]
    return obj


def put_scan(item: dict) -> None:
    _get_table().put_item(Item=item)


def get_scan(scan_id: str) -> dict | None:
    response = _get_table().query(
        KeyConditionExpression=Key("scan_id").eq(scan_id),
        Limit=1,
        ScanIndexForward=False,
    )
    items = response.get("Items", [])
    if not items:
        return None
    return _to_python(items[0])  # type: ignore[return-value]


def update_scan(scan_id: str, created_at: str, updates: dict) -> None:
    update_expr = "SET " + ", ".join(f"#{k} = :{k}" for k in updates)
    expr_names = {f"#{k}": k for k in updates}
    expr_values = {f":{k}": v for k, v in updates.items()}

    _get_table().update_item(
        Key={"scan_id": scan_id, "created_at": created_at},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )
