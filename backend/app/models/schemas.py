from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ScanType(str, Enum):
    dockerfile = "dockerfile"
    image = "image"
    kubernetes = "kubernetes"


class ScanStatus(str, Enum):
    pending = "PENDING"
    complete = "COMPLETE"
    failed = "FAILED"


class Severity(str, Enum):
    info = "INFO"
    warning = "WARNING"
    error = "ERROR"


class Finding(BaseModel):
    rule_id: str
    severity: Severity
    title: str
    description: str
    fix: str | None = None
    line: int | None = None


class DockerfileAnalyzeRequest(BaseModel):
    content: str = Field(
        ...,
        min_length=1,
        max_length=524288,
        description="Raw Dockerfile content (max 512 KB)",
    )


class KubernetesAnalyzeRequest(BaseModel):
    content: str = Field(
        ...,
        min_length=1,
        max_length=524288,
        description="Raw Kubernetes manifest YAML (max 512 KB)",
    )


class ImageAnalyzeRequest(BaseModel):
    image: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Docker image reference — e.g. nginx:1.29-alpine or python:3.12-slim",
    )


class AnalysisReport(BaseModel):
    scan_id: str
    scan_type: ScanType
    status: ScanStatus
    score: int | None = Field(default=None, ge=0, le=100)
    findings: list[Finding] = []
    fixed_dockerfile: str | None = None
    metadata: dict[str, Any] = {}
    created_at: str
    completed_at: str | None = None
