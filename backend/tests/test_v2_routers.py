"""Unit tests for Lambda v2 routers."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

# Set required env vars before importing the v2 app
os.environ.setdefault("DYNAMODB_TABLE", "test-table-v2")
os.environ.setdefault("REPORTS_BUCKET", "test-reports-bucket")
os.environ.setdefault("SBOM_BUCKET", "test-sbom-bucket")
os.environ.setdefault(
    "SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/test-queue"
)
os.environ.setdefault("ECS_CLUSTER_NAME", "test-cluster")
os.environ.setdefault("ECS_TASK_DEFINITION", "test-scanner")
os.environ.setdefault("ECS_SUBNET_IDS", "subnet-abc123")
os.environ.setdefault("ECS_SECURITY_GROUP_ID", "sg-abc123")
os.environ.setdefault("ENVIRONMENT", "test")

from v2.auth.cognito import get_current_user  # noqa: E402
from v2.main import app  # noqa: E402

TEST_USER = {
    "user_id": "user-abc-123",
    "email": "test@example.com",
    "username": "testuser",
}

VALID_DOCKERFILE = (
    "FROM python:3.12-slim\n"
    "WORKDIR /app\n"
    "COPY . .\n"
    "USER 1000\n"
    "HEALTHCHECK CMD python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8080/health')\"\n"
    'CMD ["python", "main.py"]\n'
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    yield
    app.dependency_overrides.clear()


# ── Health ─────────────────────────────────────────────────────────────────────


def test_health_v2_returns_ok():
    response = client.get("/api/v2/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "2"


# ── Auth guard ─────────────────────────────────────────────────────────────────


def test_dockerfile_analyze_requires_auth():
    app.dependency_overrides.clear()
    response = client.post(
        "/api/v2/analyze/dockerfile", json={"content": VALID_DOCKERFILE}
    )
    assert response.status_code == 401


def test_image_analyze_requires_auth():
    app.dependency_overrides.clear()
    response = client.post(
        "/api/v2/analyze/image", json={"image_name": "nginx:1.25-alpine"}
    )
    assert response.status_code == 401


def test_results_requires_auth():
    app.dependency_overrides.clear()
    response = client.get("/api/v2/results/some-scan-id")
    assert response.status_code == 401


def test_scans_list_requires_auth():
    app.dependency_overrides.clear()
    response = client.get("/api/v2/scans")
    assert response.status_code == 401


# ── Dockerfile analysis ────────────────────────────────────────────────────────


def _mock_analyze_result():
    finding = MagicMock()
    finding.model_dump.return_value = {
        "rule": "R007",
        "severity": "WARNING",
        "line": 3,
        "message": "Multiple RUN instructions",
        "fix": "Combine RUN instructions with &&",
    }
    result = MagicMock()
    result.score = 90
    result.findings = [finding]
    result.fixed_dockerfile = VALID_DOCKERFILE
    result.metadata = {"instruction_count": 6, "is_multi_stage": False}
    return result


def test_analyze_dockerfile_v2_success():
    with (
        patch("v2.routers.analyze.dynamodb.put_scan"),
        patch(
            "app.services.dockerfile_analyzer.analyze",
            return_value=_mock_analyze_result(),
        ),
    ):
        response = client.post(
            "/api/v2/analyze/dockerfile", json={"content": VALID_DOCKERFILE}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["scan_type"] == "dockerfile"
    assert data["status"] == "COMPLETE"
    assert data["score"] == 90
    assert isinstance(data["findings"], list)
    assert len(data["findings"]) == 1
    assert "scan_id" in data
    assert "created_at" in data


def test_analyze_dockerfile_v2_empty_content_rejected():
    response = client.post("/api/v2/analyze/dockerfile", json={"content": ""})
    assert response.status_code == 422


def test_analyze_dockerfile_v2_missing_body_rejected():
    response = client.post("/api/v2/analyze/dockerfile", json={})
    assert response.status_code == 422


def test_analyze_dockerfile_v2_analyzer_error_returns_422():
    with (
        patch("v2.routers.analyze.dynamodb.put_scan"),
        patch(
            "app.services.dockerfile_analyzer.analyze",
            side_effect=ValueError("parse error"),
        ),
    ):
        response = client.post(
            "/api/v2/analyze/dockerfile", json={"content": VALID_DOCKERFILE}
        )
    assert response.status_code == 422


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


def test_analyze_kubernetes_v2_success():
    with patch("v2.routers.analyze.dynamodb.put_scan"):
        response = client.post(
            "/api/v2/analyze/kubernetes", json={"content": VALID_MANIFEST}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["scan_type"] == "kubernetes"
    assert data["status"] == "COMPLETE"
    assert isinstance(data["findings"], list)
    assert "scan_id" in data


def test_analyze_kubernetes_v2_empty_content_rejected():
    response = client.post("/api/v2/analyze/kubernetes", json={"content": ""})
    assert response.status_code == 422


def test_analyze_kubernetes_v2_invalid_manifest_returns_422():
    with patch("v2.routers.analyze.dynamodb.put_scan"):
        response = client.post(
            "/api/v2/analyze/kubernetes", json={"content": "kind: ConfigMap\n"}
        )
    assert response.status_code == 422


def test_kubernetes_analyze_requires_auth():
    app.dependency_overrides.clear()
    response = client.post(
        "/api/v2/analyze/kubernetes", json={"content": VALID_MANIFEST}
    )
    assert response.status_code == 401


# ── Image scan submit ──────────────────────────────────────────────────────────


def test_analyze_image_v2_success():
    with (
        patch("v2.routers.analyze.dynamodb.put_scan"),
        patch(
            "v2.routers.analyze.ecs_launcher.launch_scan",
            return_value="arn:aws:ecs:us-east-1:123:task/cluster/taskid",
        ),
    ):
        response = client.post(
            "/api/v2/analyze/image", json={"image_name": "nginx:1.25-alpine"}
        )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "PENDING"
    assert "scan_id" in data
    assert "poll" in data["message"].lower()


def test_analyze_image_v2_missing_name_rejected():
    response = client.post("/api/v2/analyze/image", json={})
    assert response.status_code == 422


# ── Results retrieval ──────────────────────────────────────────────────────────


def test_get_results_not_found():
    with patch("v2.routers.results.dynamodb.get_scan", return_value=None):
        response = client.get("/api/v2/results/nonexistent")
    assert response.status_code == 404


def test_get_results_forbidden_for_other_user():
    record = {
        "scan_id": "scan-xyz",
        "user_id": "different-user",
        "created_at": "2026-07-06T00:00:00Z",
        "scan_type": "image",
        "status": "PENDING",
    }
    with patch("v2.routers.results.dynamodb.get_scan", return_value=record):
        response = client.get("/api/v2/results/scan-xyz")
    assert response.status_code == 403


def test_get_results_pending_has_no_urls():
    record = {
        "scan_id": "scan-abc",
        "user_id": TEST_USER["user_id"],
        "created_at": "2026-07-06T00:00:00Z",
        "scan_type": "image",
        "status": "PENDING",
        "image_name": "nginx:1.25-alpine",
    }
    with patch("v2.routers.results.dynamodb.get_scan", return_value=record):
        response = client.get("/api/v2/results/scan-abc")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["report_url"] is None
    assert data["sbom_url"] is None


def test_get_results_complete_returns_presigned_urls():
    record = {
        "scan_id": "scan-def",
        "user_id": TEST_USER["user_id"],
        "created_at": "2026-07-06T00:00:00Z",
        "scan_type": "image",
        "status": "COMPLETE",
        "image_name": "nginx:1.25-alpine",
        "report_s3_key": "scan-def/report.json",
        "sbom_s3_key": "scan-def/sbom.json",
        "cve_critical": 0,
        "cve_high": 2,
        "cve_medium": 5,
        "cve_low": 10,
    }
    with (
        patch("v2.routers.results.dynamodb.get_scan", return_value=record),
        patch("v2.routers.results._s3") as mock_s3,
    ):
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/presigned"
        response = client.get("/api/v2/results/scan-def")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETE"
    assert data["cve_high"] == 2
    assert data["cve_critical"] == 0
    assert data["report_url"] == "https://s3.example.com/presigned"
    assert data["sbom_url"] == "https://s3.example.com/presigned"


def test_get_results_complete_missing_s3_keys_has_no_urls():
    record = {
        "scan_id": "scan-ghi",
        "user_id": TEST_USER["user_id"],
        "created_at": "2026-07-06T00:00:00Z",
        "scan_type": "image",
        "status": "COMPLETE",
        "image_name": "nginx:1.25-alpine",
    }
    with patch("v2.routers.results.dynamodb.get_scan", return_value=record):
        response = client.get("/api/v2/results/scan-ghi")
    assert response.status_code == 200
    assert response.json()["report_url"] is None


# ── Scan history ───────────────────────────────────────────────────────────────


def test_list_scans_returns_history():
    items = [
        {
            "scan_id": "scan-1",
            "user_id": TEST_USER["user_id"],
            "created_at": "2026-07-06T00:00:00Z",
            "scan_type": "image",
            "status": "COMPLETE",
            "image_name": "nginx:1.25",
        },
        {
            "scan_id": "scan-2",
            "user_id": TEST_USER["user_id"],
            "created_at": "2026-07-05T00:00:00Z",
            "scan_type": "dockerfile",
            "status": "COMPLETE",
        },
    ]
    with patch(
        "v2.routers.scans.dynamodb.list_user_scans",
        return_value={"items": items, "next_token": None},
    ):
        response = client.get("/api/v2/scans")
    assert response.status_code == 200
    data = response.json()
    assert len(data["scans"]) == 2
    assert data["next_page_token"] is None


def test_list_scans_returns_pagination_token():
    with patch(
        "v2.routers.scans.dynamodb.list_user_scans",
        return_value={"items": [], "next_token": "cursor-xyz"},
    ):
        response = client.get("/api/v2/scans?limit=5")
    assert response.status_code == 200
    assert response.json()["next_page_token"] == "cursor-xyz"


def test_list_scans_limit_out_of_range_rejected():
    response = client.get("/api/v2/scans?limit=0")
    assert response.status_code == 422


def test_delete_scan_success():
    record = {"scan_id": "scan-del", "user_id": TEST_USER["user_id"]}
    with (
        patch("v2.routers.scans.dynamodb.get_scan", return_value=record),
        patch("v2.routers.scans.dynamodb.delete_scan"),
    ):
        response = client.delete("/api/v2/scans/scan-del")
    assert response.status_code == 204


def test_delete_scan_not_found():
    with patch("v2.routers.scans.dynamodb.get_scan", return_value=None):
        response = client.delete("/api/v2/scans/nonexistent")
    assert response.status_code == 404


def test_delete_scan_forbidden_for_other_user():
    record = {"scan_id": "scan-xyz", "user_id": "someone-else"}
    with patch("v2.routers.scans.dynamodb.get_scan", return_value=record):
        response = client.delete("/api/v2/scans/scan-xyz")
    assert response.status_code == 403


def test_cancel_scan_success():
    record = {
        "scan_id": "scan-cancel",
        "user_id": TEST_USER["user_id"],
        "status": "PENDING",
    }
    with (
        patch("v2.routers.scans.dynamodb.get_scan", return_value=record),
        patch("v2.routers.scans.dynamodb.cancel_scan"),
        patch("v2.routers.scans._stop_ecs_task"),
    ):
        response = client.post("/api/v2/scans/scan-cancel/cancel")
    assert response.status_code == 204


def test_cancel_scan_not_found():
    with patch("v2.routers.scans.dynamodb.get_scan", return_value=None):
        response = client.post("/api/v2/scans/nonexistent/cancel")
    assert response.status_code == 404


def test_cancel_scan_forbidden_for_other_user():
    record = {"scan_id": "scan-xyz", "user_id": "someone-else", "status": "PENDING"}
    with patch("v2.routers.scans.dynamodb.get_scan", return_value=record):
        response = client.post("/api/v2/scans/scan-xyz/cancel")
    assert response.status_code == 403


def test_cancel_scan_already_complete():
    record = {
        "scan_id": "scan-done",
        "user_id": TEST_USER["user_id"],
        "status": "COMPLETE",
    }
    with patch("v2.routers.scans.dynamodb.get_scan", return_value=record):
        response = client.post("/api/v2/scans/scan-done/cancel")
    assert response.status_code == 409


def test_cancel_scan_conditional_check_failed():
    record = {
        "scan_id": "scan-race",
        "user_id": TEST_USER["user_id"],
        "status": "PENDING",
    }
    err = ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "condition failed",
            }
        },
        "UpdateItem",
    )
    with (
        patch("v2.routers.scans.dynamodb.get_scan", return_value=record),
        patch("v2.routers.scans.dynamodb.cancel_scan", side_effect=err),
    ):
        response = client.post("/api/v2/scans/scan-race/cancel")
    assert response.status_code == 409


def test_stop_ecs_task_stops_matching_sqs_message_task():
    from v2.routers.scans import _stop_ecs_task

    scan_id = "scan-xyz"
    task_arn = "arn:aws:ecs:us-east-1:123:task/cluster/abc"
    sqs_msg = json.dumps({"scan_id": scan_id, "image_name": "nginx:latest"})
    mock_task = {
        "taskArn": task_arn,
        "overrides": {
            "containerOverrides": [
                {"environment": [{"name": "SQS_MESSAGE", "value": sqs_msg}]}
            ]
        },
    }
    mock_ecs = MagicMock()
    mock_ecs.list_tasks.return_value = {"taskArns": [task_arn]}
    mock_ecs.describe_tasks.return_value = {"tasks": [mock_task]}

    with patch("v2.routers.scans.boto3.client", return_value=mock_ecs):
        _stop_ecs_task(scan_id)

    mock_ecs.stop_task.assert_called_once_with(
        cluster="test-cluster", task=task_arn, reason="Cancelled by user"
    )


def test_stop_ecs_task_no_running_tasks():
    from v2.routers.scans import _stop_ecs_task

    mock_ecs = MagicMock()
    mock_ecs.list_tasks.return_value = {"taskArns": []}

    with patch("v2.routers.scans.boto3.client", return_value=mock_ecs):
        _stop_ecs_task("scan-none")

    mock_ecs.stop_task.assert_not_called()
