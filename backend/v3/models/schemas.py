"""Pydantic v2 request/response schemas for API v3."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_IMAGE_NAME_RE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._-]*(/[a-zA-Z0-9][a-zA-Z0-9._-]*)*"
    r"(:[a-zA-Z0-9._-]+|@sha256:[a-fA-F0-9]{64})?$"
)


class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class ScanStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ScanType(str, Enum):
    DOCKERFILE = "dockerfile"
    IMAGE = "image"
    KUBERNETES = "kubernetes"


# ── Analyze ───────────────────────────────────────────────────────────────────


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
    message: str = "Scan submitted — poll /api/v3/results/{scan_id} for status"


# ── Results / history ─────────────────────────────────────────────────────────


class ScanResult(BaseModel):
    scan_id: str
    scan_type: ScanType
    status: ScanStatus
    image_name: Optional[str] = None
    created_at: str
    score: Optional[int] = None
    cve_critical: Optional[int] = None
    cve_high: Optional[int] = None
    cve_medium: Optional[int] = None
    cve_low: Optional[int] = None
    report_url: Optional[str] = None
    sbom_url: Optional[str] = None


class ScanSummary(BaseModel):
    scan_id: str
    scan_type: ScanType
    status: ScanStatus
    created_at: str
    image_name: Optional[str] = None
    score: Optional[int] = None


class ScanHistoryResponse(BaseModel):
    scans: list[ScanSummary]
    next_page_token: Optional[str] = None


class TrendPoint(BaseModel):
    scan_id: str
    created_at: str
    score: int
    cve_critical: int = 0
    cve_high: int = 0


class TrendResponse(BaseModel):
    image_name: str
    points: list[TrendPoint]


# ── Billing ───────────────────────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    price_id: str = Field(..., description="Stripe Price ID for the selected plan")


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str


class BillingStatusResponse(BaseModel):
    tier: SubscriptionTier
    scan_count_month: int
    scan_limit: int
    period_end: Optional[str] = None
    payment_past_due: bool = False


# ── API keys ──────────────────────────────────────────────────────────────────


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=64, description="Label for this key"
    )


class ApiKeyCreateResponse(BaseModel):
    key_id: str
    name: str
    raw_key: str = Field(..., description="Shown once — copy it now")
    created_at: str


class ApiKeySummary(BaseModel):
    key_id: str
    name: str
    created_at: str
    last_used_at: Optional[str] = None
    revoked: bool


class ApiKeyListResponse(BaseModel):
    keys: list[ApiKeySummary]


# ── Org ───────────────────────────────────────────────────────────────────────


class OrgCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class OrgResponse(BaseModel):
    org_id: str
    name: str
    admin_user_id: str
    member_ids: list[str]
    created_at: str


class OrgInviteRequest(BaseModel):
    user_id: str = Field(..., description="Cognito user_id (sub) of the member to add")
