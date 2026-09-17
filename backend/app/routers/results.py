import logging

from fastapi import APIRouter, HTTPException, status

from app.db import dynamodb
from app.models.schemas import AnalysisReport, Finding, ScanStatus, ScanType

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/results/{scan_id}",
    response_model=AnalysisReport,
    summary="Retrieve a scan result by ID",
)
def get_result(scan_id: str) -> AnalysisReport:
    item = dynamodb.get_scan(scan_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan '{scan_id}' not found.",
        )

    logger.info(
        "Result retrieved", extra={"scan_id": scan_id, "status": item.get("status")}
    )

    return AnalysisReport(
        scan_id=item["scan_id"],
        scan_type=ScanType(item["scan_type"]),
        status=ScanStatus(item["status"]),
        score=item.get("score"),
        findings=[Finding.model_validate(f) for f in item.get("findings", [])],
        metadata=item.get("metadata", {}),
        created_at=item["created_at"],
        completed_at=item.get("completed_at"),
    )
