"""GET /api/v2/results/{scan_id} — poll scan status and retrieve results."""

import os

import boto3
from botocore.config import Config
from fastapi import APIRouter, Depends, HTTPException, status

from ..auth.cognito import get_current_user
from ..db import dynamodb
from ..models.schemas import ScanResult, ScanStatus, ScanType

router = APIRouter(tags=["results"])

REPORTS_BUCKET = os.environ.get("REPORTS_BUCKET", "")
SBOM_BUCKET = os.environ.get("SBOM_BUCKET", "")

_s3 = boto3.client("s3", config=Config(signature_version="s3v4"))

_PRESIGN_EXPIRY = 18000  # 5 hours


def _presigned_url(bucket: str, key: str | None) -> str | None:
    if not bucket or not key:
        return None
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=_PRESIGN_EXPIRY,
    )


@router.get("/results/{scan_id}", response_model=ScanResult)
async def get_results(
    scan_id: str,
    user: dict = Depends(get_current_user),
) -> ScanResult:
    record = dynamodb.get_scan(scan_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found"
        )
    if record.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    scan_status = ScanStatus(record.get("status", ScanStatus.PENDING.value))

    report_url = None
    sbom_url = None
    if scan_status == ScanStatus.COMPLETE:
        report_url = _presigned_url(REPORTS_BUCKET, record.get("report_s3_key"))
        sbom_url = _presigned_url(SBOM_BUCKET, record.get("sbom_s3_key"))

    return ScanResult(
        scan_id=record["scan_id"],
        scan_type=ScanType(record.get("scan_type", ScanType.IMAGE.value)),
        status=scan_status,
        image_name=record.get("image_name"),
        created_at=record.get("created_at", ""),
        cve_critical=record.get("cve_critical"),
        cve_high=record.get("cve_high"),
        cve_medium=record.get("cve_medium"),
        cve_low=record.get("cve_low"),
        report_url=report_url,
        sbom_url=sbom_url,
        score=record.get("score"),
        findings=record.get("findings"),
        fixed_dockerfile=record.get("fixed_dockerfile") or None,
    )
