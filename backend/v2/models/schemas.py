"""Pydantic v2 request/response schemas for API v2."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_IMAGE_NAME_RE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._-]*(/[a-zA-Z0-9][a-zA-Z0-9._-]*)*"
    r"(:[a-zA-Z0-9._-]+|@sha256:[a-fA-F0-9]{64})?$"
)


class ScanStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ScanType(str, Enum):
    DOCKERFILE = "dockerfile"
    IMAGE = "image"
    KUBERNETES = "kubernetes"


# ── Request schemas ───────────────────────────────────────────────────────────


class DockerfileAnalyzeRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Raw Dockerfile content")


class KubernetesAnalyzeRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Raw Kubernetes manifest YAML")


class ImageScanRequest(BaseModel):
    image_name: str = Field(
        ..., description="Docker image reference, e.g. nginx:1.25-alpine"
    )

    @field_validator("image_name")
    @classmethod
    def validate_image_name(cls, v: str) -> str:
        if not _IMAGE_NAME_RE.match(v):
            raise ValueError(
                "image_name must be a valid image reference (no leading '-', no shell metacharacters)"
            )
        return v


# ── Response schemas ──────────────────────────────────────────────────────────


class DockerfileAnalyzeResponse(BaseModel):
    scan_id: str
    scan_type: ScanType = ScanType.DOCKERFILE
    status: ScanStatus = ScanStatus.COMPLETE
    score: int
    findings: list[dict]
    fixed_dockerfile: str
    created_at: str


class ImageScanSubmitResponse(BaseModel):
    scan_id: str
    status: ScanStatus = ScanStatus.PENDING
    message: str = "Scan submitted — poll /api/v2/results/{scan_id} for status"


class CVEFinding(BaseModel):
    cve_id: str
    severity: str
    package: str
    version: str
    fixed_in: Optional[str] = None
    description: str


class ScanResult(BaseModel):
    scan_id: str
    scan_type: ScanType
    status: ScanStatus
    image_name: Optional[str] = None
    created_at: str
    # image scan fields
    cve_critical: Optional[int] = None
    cve_high: Optional[int] = None
    cve_medium: Optional[int] = None
    cve_low: Optional[int] = None
    report_url: Optional[str] = None
    sbom_url: Optional[str] = None
    # dockerfile scan fields
    score: Optional[int] = None
    findings: Optional[list[dict]] = None
    fixed_dockerfile: Optional[str] = None


class ScanSummary(BaseModel):
    scan_id: str
    scan_type: ScanType
    status: ScanStatus
    created_at: str
    image_name: Optional[str] = None


class ScanHistoryResponse(BaseModel):
    scans: list[ScanSummary]
    next_page_token: Optional[str] = None
