import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import boto3
from fastapi import APIRouter, HTTPException, status

from app.db import dynamodb
from app.models.schemas import (
    AnalysisReport,
    DockerfileAnalyzeRequest,
    ImageAnalyzeRequest,
    KubernetesAnalyzeRequest,
    ScanStatus,
    ScanType,
)
from app.services import dockerfile_analyzer, image_analyzer, k8s_manifest_analyzer

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ttl() -> int:
    ttl_days = int(os.getenv("DYNAMODB_TTL_DAYS", "90"))
    return int(time.time()) + ttl_days * 86400


def _store_report(scan_id: str, report: dict) -> str | None:
    bucket = os.getenv("REPORTS_BUCKET_NAME")
    if not bucket:
        return None
    key = f"reports/{scan_id}.json"
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(report, default=str),
        ContentType="application/json",
    )
    return key


@router.post(
    "/analyze/dockerfile",
    response_model=AnalysisReport,
    status_code=status.HTTP_200_OK,
    summary="Analyse a Dockerfile for security and best-practice issues",
)
def analyze_dockerfile(request: DockerfileAnalyzeRequest) -> AnalysisReport:
    scan_id = str(uuid.uuid4())
    created_at = _now()

    logger.info("Dockerfile analysis started", extra={"scan_id": scan_id})

    try:
        result = dockerfile_analyzer.analyze(request.content)
    except Exception as exc:
        logger.error(
            "Dockerfile analysis failed", extra={"scan_id": scan_id, "error": str(exc)}
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    completed_at = _now()

    report = AnalysisReport(
        scan_id=scan_id,
        scan_type=ScanType.dockerfile,
        status=ScanStatus.complete,
        score=result.score,
        findings=result.findings,
        fixed_dockerfile=result.fixed_dockerfile,
        metadata=result.metadata,
        created_at=created_at,
        completed_at=completed_at,
    )

    report_s3_key = _store_report(scan_id, report.model_dump())

    dynamodb.put_scan(
        {
            "scan_id": scan_id,
            "created_at": created_at,
            "scan_type": ScanType.dockerfile.value,
            "status": ScanStatus.complete.value,
            "score": result.score,
            "findings": [f.model_dump() for f in result.findings],
            "metadata": result.metadata,
            "completed_at": completed_at,
            "report_s3_key": report_s3_key,
            "ttl": _ttl(),
        }
    )

    logger.info(
        "Dockerfile analysis complete",
        extra={
            "scan_id": scan_id,
            "score": result.score,
            "finding_count": len(result.findings),
        },
    )

    return report


@router.post(
    "/analyze/kubernetes",
    response_model=AnalysisReport,
    status_code=status.HTTP_200_OK,
    summary="Analyse a Kubernetes manifest for security and best-practice issues",
)
def analyze_kubernetes(request: KubernetesAnalyzeRequest) -> AnalysisReport:
    scan_id = str(uuid.uuid4())
    created_at = _now()

    logger.info("Kubernetes manifest analysis started", extra={"scan_id": scan_id})

    try:
        result = k8s_manifest_analyzer.analyze(request.content)
    except ValueError as exc:
        logger.error(
            "Kubernetes manifest analysis failed",
            extra={"scan_id": scan_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    completed_at = _now()

    report = AnalysisReport(
        scan_id=scan_id,
        scan_type=ScanType.kubernetes,
        status=ScanStatus.complete,
        score=result.score,
        findings=result.findings,
        metadata=result.metadata,
        created_at=created_at,
        completed_at=completed_at,
    )

    report_s3_key = _store_report(scan_id, report.model_dump())

    dynamodb.put_scan(
        {
            "scan_id": scan_id,
            "created_at": created_at,
            "scan_type": ScanType.kubernetes.value,
            "status": ScanStatus.complete.value,
            "score": result.score,
            "findings": [f.model_dump() for f in result.findings],
            "metadata": result.metadata,
            "completed_at": completed_at,
            "report_s3_key": report_s3_key,
            "ttl": _ttl(),
        }
    )

    logger.info(
        "Kubernetes manifest analysis complete",
        extra={
            "scan_id": scan_id,
            "score": result.score,
            "finding_count": len(result.findings),
        },
    )

    return report


@router.post(
    "/analyze/image",
    response_model=AnalysisReport,
    status_code=status.HTTP_200_OK,
    summary="Fetch Docker image metadata from Docker Hub (no pull)",
)
def analyze_image(request: ImageAnalyzeRequest) -> AnalysisReport:
    scan_id = str(uuid.uuid4())
    created_at = _now()

    logger.info(
        "Image analysis started", extra={"scan_id": scan_id, "image": request.image}
    )

    try:
        result = image_analyzer.analyze(request.image)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        logger.error(
            "Image analysis failed", extra={"scan_id": scan_id, "error": str(exc)}
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    completed_at = _now()

    metadata = {
        "namespace": result.namespace,
        "name": result.name,
        "tag": result.tag,
        "digest": result.digest,
        "architecture": result.architecture,
        "os": result.os,
        "compressed_size_bytes": result.compressed_size_bytes,
        "layer_count": result.layer_count,
        "last_pushed": result.last_pushed,
        **result.metadata,
    }

    report = AnalysisReport(
        scan_id=scan_id,
        scan_type=ScanType.image,
        status=ScanStatus.complete,
        findings=[],
        metadata=metadata,
        created_at=created_at,
        completed_at=completed_at,
    )

    report_s3_key = _store_report(scan_id, report.model_dump())

    dynamodb.put_scan(
        {
            "scan_id": scan_id,
            "created_at": created_at,
            "scan_type": ScanType.image.value,
            "status": ScanStatus.complete.value,
            "metadata": metadata,
            "completed_at": completed_at,
            "report_s3_key": report_s3_key,
            "ttl": _ttl(),
        }
    )

    logger.info(
        "Image analysis complete", extra={"scan_id": scan_id, "image": request.image}
    )

    return report
