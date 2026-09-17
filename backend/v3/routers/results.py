"""
GET /api/v3/results/{scan_id}                       — fetch single scan result
GET /api/v3/scans                                   — paginated scan history
GET /api/v3/scans/trend?image_name=...              — score trend for one image
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth.cognito import get_current_user
from ..db import dynamodb as db
from ..models.schemas import (
    ScanHistoryResponse,
    ScanResult,
    ScanStatus,
    ScanSummary,
    ScanType,
    TrendPoint,
    TrendResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["results"])


def _to_scan_result(item: dict) -> ScanResult:
    return ScanResult(
        scan_id=item["scan_id"],
        scan_type=ScanType(item.get("scan_type", "dockerfile")),
        status=ScanStatus(item.get("status", "COMPLETE")),
        image_name=item.get("image_name"),
        created_at=item["created_at"],
        score=item.get("score"),
        cve_critical=item.get("cve_critical"),
        cve_high=item.get("cve_high"),
        cve_medium=item.get("cve_medium"),
        cve_low=item.get("cve_low"),
        report_url=item.get("report_url"),
        sbom_url=item.get("sbom_url"),
    )


@router.get("/results/{scan_id}", response_model=ScanResult)
async def get_result(
    scan_id: str,
    user: dict = Depends(get_current_user),
) -> ScanResult:
    item = db.get_scan(scan_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found"
        )
    if item.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return _to_scan_result(item)


@router.get("/scans", response_model=ScanHistoryResponse)
async def list_scans(
    limit: int = Query(20, ge=1, le=100),
    next_page_token: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> ScanHistoryResponse:
    result = db.list_user_scans(
        user["user_id"], limit=limit, next_token=next_page_token
    )
    summaries = [
        ScanSummary(
            scan_id=item["scan_id"],
            scan_type=ScanType(item.get("scan_type", "dockerfile")),
            status=ScanStatus(item.get("status", "COMPLETE")),
            created_at=item["created_at"],
            image_name=item.get("image_name"),
            score=item.get("score"),
        )
        for item in result["items"]
    ]
    return ScanHistoryResponse(
        scans=summaries, next_page_token=result.get("next_token")
    )


@router.get("/scans/trend", response_model=TrendResponse)
async def get_trend(
    image_name: str = Query(..., description="Docker image reference to trend"),
    user: dict = Depends(get_current_user),
) -> TrendResponse:
    items = db.list_image_scans(user["user_id"], image_name)
    points = [
        TrendPoint(
            scan_id=item["scan_id"],
            created_at=item["created_at"],
            score=item.get("score", 0),
            cve_critical=item.get("cve_critical", 0),
            cve_high=item.get("cve_high", 0),
        )
        for item in items
        if item.get("score") is not None
    ]
    return TrendResponse(image_name=image_name, points=points)
