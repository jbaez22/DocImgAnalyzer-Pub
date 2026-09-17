import os
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# Set required env vars before importing the app
os.environ.setdefault("DYNAMODB_TABLE_NAME", "test-table")
os.environ.setdefault("REPORTS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("ENVIRONMENT", "test")

from app.main import app  # noqa: E402

client = TestClient(app)

VALID_DOCKERFILE = """\
FROM python:3.12-slim
WORKDIR /app
COPY . .
USER 1000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"
CMD ["python", "main.py"]
"""


# ── Health ─────────────────────────────────────────────────────────────────────


def test_health_returns_ok():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ── Dockerfile analysis ────────────────────────────────────────────────────────


def test_analyze_dockerfile_success():
    with (
        patch("app.routers.analyze.dynamodb.put_scan"),
        patch("app.routers.analyze._store_report", return_value="reports/test.json"),
    ):
        response = client.post(
            "/api/v1/analyze/dockerfile", json={"content": VALID_DOCKERFILE}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["scan_type"] == "dockerfile"
    assert data["status"] == "COMPLETE"
    assert isinstance(data["score"], int)
    assert isinstance(data["findings"], list)
    assert "scan_id" in data
    assert "created_at" in data


def test_analyze_dockerfile_empty_content_rejected():
    response = client.post("/api/v1/analyze/dockerfile", json={"content": ""})
    assert response.status_code == 422


def test_analyze_dockerfile_missing_body_rejected():
    response = client.post("/api/v1/analyze/dockerfile", json={})
    assert response.status_code == 422


VALID_MANIFEST = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
spec:
  template:
    spec:
      containers:
        - name: web
          image: nginx:1.29-alpine
"""


def test_analyze_kubernetes_success():
    with (
        patch("app.routers.analyze.dynamodb.put_scan"),
        patch("app.routers.analyze._store_report", return_value="reports/test.json"),
    ):
        response = client.post(
            "/api/v1/analyze/kubernetes", json={"content": VALID_MANIFEST}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["scan_type"] == "kubernetes"
    assert data["status"] == "COMPLETE"
    assert isinstance(data["score"], int)
    assert isinstance(data["findings"], list)
    assert "scan_id" in data


def test_analyze_kubernetes_empty_content_rejected():
    response = client.post("/api/v1/analyze/kubernetes", json={"content": ""})
    assert response.status_code == 422


def test_analyze_kubernetes_invalid_manifest_returns_422():
    with (
        patch("app.routers.analyze.dynamodb.put_scan"),
        patch("app.routers.analyze._store_report", return_value="reports/test.json"),
    ):
        response = client.post(
            "/api/v1/analyze/kubernetes", json={"content": "kind: ConfigMap\n"}
        )
    assert response.status_code == 422


# ── Image analysis ─────────────────────────────────────────────────────────────


def test_analyze_image_success():
    mock_result = MagicMock()
    mock_result.namespace = "library"
    mock_result.name = "nginx"
    mock_result.tag = "1.29-alpine"
    mock_result.digest = "sha256:abc"
    mock_result.architecture = "amd64"
    mock_result.os = "linux"
    mock_result.compressed_size_bytes = 20_000_000
    mock_result.layer_count = 5
    mock_result.last_pushed = "2024-06-01T00:00:00Z"
    mock_result.metadata = {}

    with (
        patch("app.routers.analyze.image_analyzer.analyze", return_value=mock_result),
        patch("app.routers.analyze.dynamodb.put_scan"),
        patch("app.routers.analyze._store_report", return_value="reports/test.json"),
    ):
        response = client.post(
            "/api/v1/analyze/image", json={"image": "nginx:1.29-alpine"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["scan_type"] == "image"
    assert data["status"] == "COMPLETE"
    assert data["metadata"]["name"] == "nginx"


def test_analyze_image_not_found_returns_404():
    with patch(
        "app.routers.analyze.image_analyzer.analyze",
        side_effect=ValueError("not found"),
    ):
        response = client.post(
            "/api/v1/analyze/image", json={"image": "nobody/fake:v9"}
        )
    assert response.status_code == 404


def test_analyze_image_upstream_error_returns_502():
    with patch(
        "app.routers.analyze.image_analyzer.analyze",
        side_effect=RuntimeError("hub down"),
    ):
        response = client.post("/api/v1/analyze/image", json={"image": "nginx:latest"})
    assert response.status_code == 502


# ── Results retrieval ──────────────────────────────────────────────────────────


def test_get_result_not_found():
    with patch("app.routers.results.dynamodb.get_scan", return_value=None):
        response = client.get("/api/v1/results/nonexistent-scan-id")
    assert response.status_code == 404


def test_get_result_found():
    mock_item = {
        "scan_id": "abc-123",
        "created_at": "2024-06-01T00:00:00Z",
        "scan_type": "dockerfile",
        "status": "COMPLETE",
        "score": 85,
        "findings": [],
        "metadata": {"instruction_count": 6},
        "completed_at": "2024-06-01T00:00:01Z",
    }
    with patch("app.routers.results.dynamodb.get_scan", return_value=mock_item):
        response = client.get("/api/v1/results/abc-123")

    assert response.status_code == 200
    data = response.json()
    assert data["scan_id"] == "abc-123"
    assert data["score"] == 85
    assert data["status"] == "COMPLETE"
