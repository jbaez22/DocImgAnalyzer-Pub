"""
POST /api/v3/analyze/dockerfile — sync Dockerfile analysis with entitlement check
POST /api/v3/analyze/image     — async image scan (Pro/Enterprise only)

No API Gateway authorizer on these routes — callers may use JWT OR X-Api-Key.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth.cognito import get_current_user_or_api_key
from ..db import dynamodb as db
from ..middleware.entitlements import check_scan_quota, require_image_scan
from ..models.schemas import (
    DockerfileAnalyzeRequest,
    DockerfileAnalyzeResponse,
    ImageScanRequest,
    ImageScanSubmitResponse,
    KubernetesAnalyzeRequest,
    ScanStatus,
    ScanType,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analyze"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/analyze/dockerfile", response_model=DockerfileAnalyzeResponse)
async def analyze_dockerfile(
    payload: DockerfileAnalyzeRequest,
    user: dict = Depends(get_current_user_or_api_key),
) -> DockerfileAnalyzeResponse:
    check_scan_quota(user["user_id"])

    from app.services.dockerfile_analyzer import analyze  # noqa: PLC0415

    scan_id = str(uuid.uuid4())
    created_at = _now()

    try:
        result = analyze(payload.content)
    except Exception as exc:
        logger.error(
            "Dockerfile analysis failed", extra={"scan_id": scan_id, "error": str(exc)}
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    findings_dicts = [f.model_dump() for f in result.findings]

    db.put_scan(
        {
            "scan_id": scan_id,
            "user_id": user["user_id"],
            "created_at": created_at,
            "scan_type": ScanType.DOCKERFILE.value,
            "status": ScanStatus.COMPLETE.value,
            "score": result.score,
            "findings": findings_dicts,
            "fixed_dockerfile": result.fixed_dockerfile or "",
            "metadata": result.metadata,
        }
    )
    db.increment_scan_count(user["user_id"])

    logger.info(
        "Dockerfile analysis complete",
        extra={"scan_id": scan_id, "score": result.score, "user_id": user["user_id"]},
    )

    return DockerfileAnalyzeResponse(
        scan_id=scan_id,
        score=result.score,
        findings=findings_dicts,
        fixed_dockerfile=result.fixed_dockerfile or "",
        created_at=created_at,
    )


@router.post("/analyze/kubernetes", response_model=DockerfileAnalyzeResponse)
async def analyze_kubernetes(
    payload: KubernetesAnalyzeRequest,
    user: dict = Depends(get_current_user_or_api_key),
) -> DockerfileAnalyzeResponse:
    check_scan_quota(user["user_id"])

    from app.services.k8s_manifest_analyzer import analyze  # noqa: PLC0415

    scan_id = str(uuid.uuid4())
    created_at = _now()

    try:
        result = analyze(payload.content)
    except ValueError as exc:
        logger.error(
            "Kubernetes manifest analysis failed",
            extra={"scan_id": scan_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    findings_dicts = [f.model_dump() for f in result.findings]

    db.put_scan(
        {
            "scan_id": scan_id,
            "user_id": user["user_id"],
            "created_at": created_at,
            "scan_type": ScanType.KUBERNETES.value,
            "status": ScanStatus.COMPLETE.value,
            "score": result.score,
            "findings": findings_dicts,
            "fixed_dockerfile": "",
            "metadata": result.metadata,
        }
    )
    db.increment_scan_count(user["user_id"])

    logger.info(
        "Kubernetes manifest analysis complete",
        extra={"scan_id": scan_id, "score": result.score, "user_id": user["user_id"]},
    )

    return DockerfileAnalyzeResponse(
        scan_id=scan_id,
        scan_type=ScanType.KUBERNETES,
        score=result.score,
        findings=findings_dicts,
        fixed_dockerfile="",
        created_at=created_at,
    )


@router.post("/analyze/image", response_model=ImageScanSubmitResponse, status_code=202)
async def analyze_image(
    payload: ImageScanRequest,
    user: dict = Depends(get_current_user_or_api_key),
) -> ImageScanSubmitResponse:
    require_image_scan(user["user_id"])
    check_scan_quota(user["user_id"])

    from v2.services import ecs_launcher  # noqa: PLC0415

    scan_id = str(uuid.uuid4())
    created_at = _now()

    db.put_scan(
        {
            "scan_id": scan_id,
            "user_id": user["user_id"],
            "created_at": created_at,
            "scan_type": ScanType.IMAGE.value,
            "status": ScanStatus.PENDING.value,
            "image_name": payload.image_name,
        }
    )
    db.increment_scan_count(user["user_id"])

    ecs_launcher.launch_scan(
        scan_id=scan_id,
        image_name=payload.image_name,
        user_id=user["user_id"],
    )

    logger.info(
        "Image scan submitted",
        extra={
            "scan_id": scan_id,
            "image": payload.image_name,
            "user_id": user["user_id"],
        },
    )

    return ImageScanSubmitResponse(scan_id=scan_id)
