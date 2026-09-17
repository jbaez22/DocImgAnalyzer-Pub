"""Unit tests for Lambda v3 routers — billing, API keys, orgs, analyze, results."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Set required env vars before importing the v3 app
os.environ.setdefault("SUBSCRIPTIONS_TABLE", "test-subscriptions")
os.environ.setdefault("API_KEYS_TABLE", "test-api-keys")
os.environ.setdefault("ORGS_TABLE", "test-orgs")
os.environ.setdefault("DYNAMODB_V2_TABLE", "test-scans-v2")
os.environ.setdefault("DYNAMODB_TABLE", "test-scans-v2")
os.environ.setdefault("REPORTS_BUCKET", "test-reports")
os.environ.setdefault("SBOM_BUCKET", "test-sbom")
os.environ.setdefault("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/test-q")
os.environ.setdefault("ECS_CLUSTER_NAME", "test-cluster")
os.environ.setdefault("ECS_TASK_DEFINITION", "test-scanner")
os.environ.setdefault("ECS_SUBNET_IDS", "subnet-abc")
os.environ.setdefault("ECS_SECURITY_GROUP_ID", "sg-abc")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("STRIPE_SECRET_MANAGER_PATH", "img-analyzer/test/stripe")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro_test")
os.environ.setdefault("STRIPE_ENTERPRISE_PRICE_ID", "price_enterprise_test")

from v3.auth.cognito import get_current_user, get_current_user_or_api_key  # noqa: E402
from v3.main import app  # noqa: E402

TEST_USER = {
    "user_id": "user-v3-abc",
    "email": "v3test@example.com",
    "username": "v3testuser",
    "auth_method": "jwt",
}

VALID_DOCKERFILE = (
    "FROM python:3.12-slim\n"
    "WORKDIR /app\n"
    "COPY . .\n"
    "USER 1000\n"
    'HEALTHCHECK CMD python -c "import urllib.request"\n'
    'CMD ["python", "main.py"]\n'
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: TEST_USER
    yield
    app.dependency_overrides.clear()


# ── Health ─────────────────────────────────────────────────────────────────────


def test_health():
    resp = client.get("/api/v3/health")
    assert resp.status_code == 200
    assert resp.json()["version"] == "3"


# ── Analyze — Dockerfile ───────────────────────────────────────────────────────


@patch("v3.middleware.entitlements.db")
@patch("v3.routers.analyze.db")
def test_analyze_dockerfile_ok(mock_db, mock_ent_db):
    sub = {"tier": "pro", "scan_count_month": 0, "scan_limit": 200}
    mock_db.get_subscription.return_value = sub
    mock_ent_db.get_subscription.return_value = sub
    mock_db.put_scan.return_value = None
    mock_db.increment_scan_count.return_value = None

    resp = client.post("/api/v3/analyze/dockerfile", json={"content": VALID_DOCKERFILE})
    assert resp.status_code == 200
    data = resp.json()
    assert "scan_id" in data
    assert data["score"] == 90  # -10 for R008 (single-stage build)
    assert data["status"] == "COMPLETE"


@patch("v3.middleware.entitlements.db")
@patch("v3.routers.analyze.db")
def test_analyze_dockerfile_quota_exceeded(mock_db, mock_ent_db):
    sub = {"tier": "free", "scan_count_month": 10, "scan_limit": 10}
    mock_db.get_subscription.return_value = sub
    mock_ent_db.get_subscription.return_value = sub
    resp = client.post("/api/v3/analyze/dockerfile", json={"content": VALID_DOCKERFILE})
    assert resp.status_code == 429
    assert "scan limit" in resp.json()["detail"].lower()


@patch("v3.middleware.entitlements.db")
@patch("v3.routers.analyze.db")
def test_analyze_dockerfile_empty_content(mock_db, mock_ent_db):
    mock_db.get_subscription.return_value = {"tier": "pro", "scan_count_month": 0}
    mock_ent_db.get_subscription.return_value = {"tier": "pro", "scan_count_month": 0}
    resp = client.post("/api/v3/analyze/dockerfile", json={"content": ""})
    assert resp.status_code == 422


VALID_MANIFEST = (
    "apiVersion: apps/v1\n"
    "kind: Deployment\n"
    "metadata:\n"
    "  name: web-app\n"
    "spec:\n"
    "  template:\n"
    "    spec:\n"
    "      containers:\n"
    "        - name: web\n"
    "          image: nginx:1.29-alpine\n"
)


@patch("v3.middleware.entitlements.db")
@patch("v3.routers.analyze.db")
def test_analyze_kubernetes_ok(mock_db, mock_ent_db):
    sub = {"tier": "pro", "scan_count_month": 0, "scan_limit": 200}
    mock_db.get_subscription.return_value = sub
    mock_ent_db.get_subscription.return_value = sub
    mock_db.put_scan.return_value = None
    mock_db.increment_scan_count.return_value = None

    resp = client.post("/api/v3/analyze/kubernetes", json={"content": VALID_MANIFEST})
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan_type"] == "kubernetes"
    assert data["status"] == "COMPLETE"
    assert "scan_id" in data


@patch("v3.middleware.entitlements.db")
@patch("v3.routers.analyze.db")
def test_analyze_kubernetes_quota_exceeded(mock_db, mock_ent_db):
    sub = {"tier": "free", "scan_count_month": 10, "scan_limit": 10}
    mock_db.get_subscription.return_value = sub
    mock_ent_db.get_subscription.return_value = sub
    resp = client.post("/api/v3/analyze/kubernetes", json={"content": VALID_MANIFEST})
    assert resp.status_code == 429


@patch("v3.middleware.entitlements.db")
@patch("v3.routers.analyze.db")
def test_analyze_kubernetes_empty_content(mock_db, mock_ent_db):
    mock_db.get_subscription.return_value = {"tier": "pro", "scan_count_month": 0}
    mock_ent_db.get_subscription.return_value = {"tier": "pro", "scan_count_month": 0}
    resp = client.post("/api/v3/analyze/kubernetes", json={"content": ""})
    assert resp.status_code == 422


# ── Analyze — Image ────────────────────────────────────────────────────────────


@patch("v3.middleware.entitlements.db")
@patch("v3.routers.analyze.db")
def test_analyze_image_requires_pro(mock_db, mock_ent_db):
    sub = {"tier": "free", "scan_count_month": 0, "scan_limit": 10}
    mock_db.get_subscription.return_value = sub
    mock_ent_db.get_subscription.return_value = sub
    resp = client.post("/api/v3/analyze/image", json={"image_name": "nginx:latest"})
    assert resp.status_code == 403
    assert "Pro" in resp.json()["detail"]


# ── Billing — status ───────────────────────────────────────────────────────────


@patch("v3.routers.billing.db")
def test_billing_status_free(mock_db):
    mock_db.get_subscription.return_value = {
        "user_id": TEST_USER["user_id"],
        "tier": "free",
        "scan_count_month": 3,
        "scan_limit": 10,
        "period_end": None,
        "payment_past_due": False,
    }
    resp = client.get("/api/v3/billing/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert data["scan_count_month"] == 3
    assert data["scan_limit"] == 10


@patch("v3.routers.billing.db")
def test_billing_status_pro(mock_db):
    mock_db.get_subscription.return_value = {
        "tier": "pro",
        "scan_count_month": 47,
        "scan_limit": 200,
        "period_end": "2026-08-01T00:00:00+00:00",
        "payment_past_due": False,
    }
    resp = client.get("/api/v3/billing/status")
    assert resp.status_code == 200
    assert resp.json()["tier"] == "pro"
    assert resp.json()["scan_limit"] == 200


@patch("v3.routers.billing.stripe_service")
@patch("v3.routers.billing.db")
def test_billing_checkout(mock_db, mock_stripe):
    mock_db.get_subscription.return_value = {"tier": "free", "scan_count_month": 0}
    mock_stripe.create_checkout_session.return_value = (
        "https://checkout.stripe.com/pay/cs_test"
    )
    resp = client.post("/api/v3/billing/checkout", json={"price_id": "price_pro_test"})
    assert resp.status_code == 200
    assert "checkout_url" in resp.json()


@patch("v3.routers.billing.stripe_service")
@patch("v3.routers.billing.db")
def test_billing_portal_no_subscription(mock_db, mock_stripe):
    mock_db.get_subscription.return_value = {
        "tier": "free",
        "scan_count_month": 0,
        "stripe_customer_id": None,
    }
    resp = client.post("/api/v3/billing/portal")
    assert resp.status_code == 400
    assert "checkout" in resp.json()["detail"].lower()


# ── API keys ───────────────────────────────────────────────────────────────────


@patch("v3.routers.api_keys.api_key_service")
def test_create_api_key(mock_svc):
    mock_svc.create_api_key.return_value = {
        "key_id": "key-abc",
        "name": "CI key",
        "raw_key": "dia_deadbeef",
        "created_at": "2026-07-08T00:00:00+00:00",
    }
    resp = client.post("/api/v3/keys", json={"name": "CI key"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["raw_key"] == "dia_deadbeef"
    assert "key_id" in data


@patch("v3.routers.api_keys.api_key_service")
def test_list_api_keys(mock_svc):
    mock_svc.list_api_keys.return_value = [
        {
            "key_id": "key-1",
            "name": "key one",
            "created_at": "2026-07-01T00:00:00+00:00",
            "last_used_at": None,
            "revoked": False,
        }
    ]
    resp = client.get("/api/v3/keys")
    assert resp.status_code == 200
    assert len(resp.json()["keys"]) == 1


@patch("v3.routers.api_keys.api_key_service")
def test_revoke_api_key(mock_svc):
    mock_svc.revoke_api_key.return_value = None
    resp = client.delete("/api/v3/keys/key-abc")
    assert resp.status_code == 204


# ── Results ────────────────────────────────────────────────────────────────────


@patch("v3.routers.results.db")
def test_get_result_ok(mock_db):
    mock_db.get_scan.return_value = {
        "scan_id": "scan-xyz",
        "user_id": TEST_USER["user_id"],
        "scan_type": "dockerfile",
        "status": "COMPLETE",
        "created_at": "2026-07-08T00:00:00+00:00",
        "score": 85,
    }
    resp = client.get("/api/v3/results/scan-xyz")
    assert resp.status_code == 200
    assert resp.json()["score"] == 85


@patch("v3.routers.results.db")
def test_get_result_not_found(mock_db):
    mock_db.get_scan.return_value = None
    resp = client.get("/api/v3/results/missing-scan")
    assert resp.status_code == 404


@patch("v3.routers.results.db")
def test_get_result_forbidden(mock_db):
    mock_db.get_scan.return_value = {
        "scan_id": "scan-other",
        "user_id": "other-user-id",
        "scan_type": "dockerfile",
        "status": "COMPLETE",
        "created_at": "2026-07-08T00:00:00+00:00",
    }
    resp = client.get("/api/v3/results/scan-other")
    assert resp.status_code == 403


@patch("v3.routers.results.db")
def test_list_scans(mock_db):
    mock_db.list_user_scans.return_value = {
        "items": [
            {
                "scan_id": "scan-1",
                "scan_type": "dockerfile",
                "status": "COMPLETE",
                "created_at": "2026-07-08T00:00:00+00:00",
                "score": 90,
            }
        ],
        "next_token": None,
    }
    resp = client.get("/api/v3/scans")
    assert resp.status_code == 200
    assert len(resp.json()["scans"]) == 1


@patch("v3.routers.results.db")
def test_get_trend(mock_db):
    mock_db.list_image_scans.return_value = [
        {
            "scan_id": "s1",
            "created_at": "2026-06-01T00:00:00+00:00",
            "score": 70,
            "cve_critical": 0,
            "cve_high": 2,
        },
        {
            "scan_id": "s2",
            "created_at": "2026-07-01T00:00:00+00:00",
            "score": 85,
            "cve_critical": 0,
            "cve_high": 0,
        },
    ]
    resp = client.get("/api/v3/scans/trend?image_name=nginx:1.25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["image_name"] == "nginx:1.25"
    assert len(data["points"]) == 2
    assert data["points"][1]["score"] == 85


# ── Orgs ───────────────────────────────────────────────────────────────────────


@patch("v3.routers.orgs.org_service")
def test_create_org_enterprise(mock_svc):
    mock_svc.create_org.return_value = {
        "org_id": "org-abc",
        "name": "Acme Corp",
        "admin_user_id": TEST_USER["user_id"],
        "member_ids": [TEST_USER["user_id"]],
        "created_at": "2026-07-08T00:00:00+00:00",
    }
    resp = client.post("/api/v3/orgs", json={"name": "Acme Corp"})
    assert resp.status_code == 201
    assert resp.json()["org_id"] == "org-abc"


@patch("v3.routers.orgs.org_service")
def test_get_my_org(mock_svc):
    mock_svc.get_org.return_value = {
        "org_id": "org-abc",
        "name": "Acme Corp",
        "admin_user_id": TEST_USER["user_id"],
        "member_ids": [TEST_USER["user_id"]],
        "created_at": "2026-07-08T00:00:00+00:00",
    }
    resp = client.get("/api/v3/orgs/me")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Acme Corp"
