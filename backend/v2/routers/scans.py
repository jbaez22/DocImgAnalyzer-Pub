"""
GET    /api/v2/scans                   — list authenticated user's scan history
DELETE /api/v2/scans/{scan_id}         — delete a scan from history
POST   /api/v2/scans/{scan_id}/cancel  — cancel a pending/processing scan
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth.cognito import get_current_user
from ..db import dynamodb
from ..models.schemas import ScanHistoryResponse, ScanStatus, ScanSummary, ScanType

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scans"])


def _stop_ecs_task(scan_id: str) -> None:
    """Best-effort: find and stop the ECS Fargate task for this scan."""
    cluster = os.environ.get("ECS_CLUSTER_NAME", "")
    if not cluster:
        return
    try:
        ecs = boto3.client(
            "ecs", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        )
        task_arns = ecs.list_tasks(cluster=cluster, desiredStatus="RUNNING").get(
            "taskArns", []
        )
        if not task_arns:
            return
        tasks = ecs.describe_tasks(cluster=cluster, tasks=task_arns).get("tasks", [])
        for task in tasks:
            for override in task.get("overrides", {}).get("containerOverrides", []):
                for env in override.get("environment", []):
                    matched = False
                    if env["name"] == "SQS_MESSAGE":
                        try:
                            body = json.loads(env["value"])
                            matched = body.get("scan_id") == scan_id
                        except (json.JSONDecodeError, KeyError):
                            pass
                    elif env["name"] == "SCAN_ID":
                        matched = env["value"] == scan_id
                    if matched:
                        ecs.stop_task(
                            cluster=cluster,
                            task=task["taskArn"],
                            reason="Cancelled by user",
                        )
                        logger.info(
                            "Stopped ECS task %s for scan %s", task["taskArn"], scan_id
                        )
                        return
    except Exception:
        logger.exception("Failed to stop ECS task for scan %s (best-effort)", scan_id)


@router.get("/scans", response_model=ScanHistoryResponse)
async def list_scans(
    limit: int = Query(default=20, ge=1, le=100),
    page_token: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
) -> ScanHistoryResponse:
    result = dynamodb.list_user_scans(
        user_id=user["user_id"],
        limit=limit,
        next_token=page_token,
    )
    scans = [
        ScanSummary(
            scan_id=item["scan_id"],
            scan_type=ScanType(item.get("scan_type", ScanType.IMAGE.value)),
            status=ScanStatus(item.get("status", ScanStatus.PENDING.value)),
            created_at=item.get("created_at", ""),
            image_name=item.get("image_name"),
        )
        for item in result["items"]
    ]
    return ScanHistoryResponse(scans=scans, next_page_token=result.get("next_token"))


@router.delete("/scans/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(
    scan_id: str,
    user: dict = Depends(get_current_user),
) -> None:
    record = dynamodb.get_scan(scan_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found"
        )
    if record.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    dynamodb.delete_scan(scan_id)


@router.post("/scans/{scan_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_scan(
    scan_id: str,
    user: dict = Depends(get_current_user),
) -> None:
    record = dynamodb.get_scan(scan_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found"
        )
    if record.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    current_status = record.get("status", "")
    if current_status not in ("PENDING", "PROCESSING"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel a scan with status {current_status}",
        )
    try:
        dynamodb.cancel_scan(scan_id)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Scan already completed or cancelled",
            )
        raise
    _stop_ecs_task(scan_id)
