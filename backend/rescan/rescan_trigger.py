"""
Nightly re-scan trigger — invoked by EventBridge Scheduler at 02:00 UTC.

For every Pro/Enterprise user with rescan_subscribed=True, finds their most
recently scanned images and launches an ECS Fargate scanner task directly
(same pattern as Lambda v2 ecs_launcher). Results are written back to the
scans-v2 DynamoDB table by the scanner container.
"""

import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SUBSCRIPTIONS_TABLE = os.environ["SUBSCRIPTIONS_TABLE"]
SCANS_V2_TABLE = os.environ["SCANS_V2_TABLE"]
ECS_CLUSTER = os.environ["ECS_CLUSTER"]
ECS_TASK_FAMILY = os.environ["ECS_TASK_FAMILY"]
ECS_SUBNET_IDS = os.environ["ECS_SUBNET_IDS"]
ECS_SECURITY_GROUP = os.environ["ECS_SECURITY_GROUP"]
MAX_IMAGES_PER_USER = int(os.environ.get("MAX_IMAGES_PER_USER", "3"))

_ddb = boto3.resource("dynamodb")
_ecs = boto3.client("ecs")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_rescan_users() -> list[dict]:
    """Return all Pro/Enterprise subscriptions that opted in to nightly re-scan."""
    response = _ddb.Table(SUBSCRIPTIONS_TABLE).scan(
        FilterExpression="(#tier = :pro OR #tier = :enterprise) AND #rs = :t",
        ExpressionAttributeNames={
            "#tier": "tier",
            "#rs": "rescan_subscribed",
        },
        ExpressionAttributeValues={
            ":pro": "pro",
            ":enterprise": "enterprise",
            ":t": True,
        },
    )
    return response.get("Items", [])


def _get_recent_images(user_id: str) -> list[str]:
    """Return the most recently scanned distinct image names for a user."""
    response = _ddb.Table(SCANS_V2_TABLE).query(
        IndexName="user-scans-index",
        KeyConditionExpression=Key("user_id").eq(user_id),
        FilterExpression="#st = :complete AND scan_type = :image",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={
            ":complete": "COMPLETE",
            ":image": "image",
        },
        ScanIndexForward=False,
        Limit=50,
    )
    seen: set[str] = set()
    images: list[str] = []
    for item in response.get("Items", []):
        name = item.get("image_name", "")
        if name and name not in seen:
            seen.add(name)
            images.append(name)
        if len(images) >= MAX_IMAGES_PER_USER:
            break
    return images


def _create_scan_record(user_id: str, image_name: str) -> str:
    """Write a PENDING scan record and return the new scan_id."""
    scan_id = str(uuid.uuid4())
    _ddb.Table(SCANS_V2_TABLE).put_item(
        Item={
            "scan_id": scan_id,
            "user_id": user_id,
            "scan_type": "image",
            "status": "PENDING",
            "image_name": image_name,
            "created_at": _now(),
            "rescan": True,
        }
    )
    return scan_id


def _launch_ecs_task(scan_id: str, image_name: str) -> None:
    """Launch a Fargate scanner task directly — same pattern as Lambda v2 ecs_launcher."""
    _ecs.run_task(
        cluster=ECS_CLUSTER,
        taskDefinition=ECS_TASK_FAMILY,
        launchType="FARGATE",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": ECS_SUBNET_IDS.split(","),
                "securityGroups": [ECS_SECURITY_GROUP],
                "assignPublicIp": "ENABLED",
            }
        },
        overrides={
            "containerOverrides": [
                {
                    "name": "scanner",
                    "environment": [
                        {"name": "SCAN_ID", "value": scan_id},
                        {"name": "IMAGE_NAME", "value": image_name},
                    ],
                }
            ]
        },
    )


def handler(event: dict, context: object) -> dict:
    logger.info("Nightly rescan started", extra={"event": event})

    users = _get_rescan_users()
    total = 0
    skipped = 0

    for sub in users:
        user_id = sub["user_id"]
        images = _get_recent_images(user_id)

        if not images:
            logger.info(
                "No completed image scans for user — skipping",
                extra={"user_id": user_id},
            )
            skipped += 1
            continue

        for image_name in images:
            scan_id = _create_scan_record(user_id, image_name)
            _launch_ecs_task(scan_id, image_name)
            total += 1
            logger.info(
                "Re-scan launched",
                extra={
                    "user_id": user_id,
                    "image_name": image_name,
                    "scan_id": scan_id,
                },
            )

    result = {
        "scans_queued": total,
        "users_skipped": skipped,
        "users_processed": len(users) - skipped,
    }
    logger.info("Nightly rescan complete", extra=result)
    return result
