import pytest
import httpx
from unittest.mock import MagicMock, patch

from app.services import image_analyzer


def test_parse_official_image_with_tag():
    ns, name, tag = image_analyzer._parse_image_ref("nginx:1.29-alpine")
    assert ns == "library"
    assert name == "nginx"
    assert tag == "1.29-alpine"


def test_parse_official_image_no_tag():
    ns, name, tag = image_analyzer._parse_image_ref("nginx")
    assert ns == "library"
    assert name == "nginx"
    assert tag == "latest"


def test_parse_user_scoped_image():
    ns, name, tag = image_analyzer._parse_image_ref("myuser/myrepo:v2.0")
    assert ns == "myuser"
    assert name == "myrepo"
    assert tag == "v2.0"


def test_parse_python_slim():
    ns, name, tag = image_analyzer._parse_image_ref("python:3.12-slim")
    assert ns == "library"
    assert name == "python"
    assert tag == "3.12-slim"


def _mock_hub_response():
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "last_pushed": "2024-06-01T00:00:00Z",
        "full_size": 20000000,
        "tag_status": "active",
        "tag_last_pulled": "2024-06-10T00:00:00Z",
        "media_type": "application/vnd.docker.distribution.manifest.list.v2+json",
        "images": [
            {
                "architecture": "amd64",
                "os": "linux",
                "digest": "sha256:abc123def456",
                "size": 20000000,
                "layers": [{"digest": "sha256:layer1"}, {"digest": "sha256:layer2"}],
            },
            {
                "architecture": "arm64",
                "os": "linux",
                "digest": "sha256:arm123",
                "size": 18000000,
                "layers": [{"digest": "sha256:alayer1"}],
            },
        ],
    }
    return mock


def test_analyze_success_prefers_amd64():
    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = (
            _mock_hub_response()
        )
        result = image_analyzer.analyze("nginx:1.29-alpine")

    assert result.architecture == "amd64"
    assert result.os == "linux"
    assert result.digest == "sha256:abc123def456"
    assert result.layer_count == 2
    assert result.namespace == "library"
    assert result.name == "nginx"
    assert result.tag == "1.29-alpine"


def test_analyze_image_not_found():
    mock_response = MagicMock()
    mock_response.status_code = 404
    error = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_response
    )

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = error
        with pytest.raises(ValueError, match="not found"):
            image_analyzer.analyze("nobody/doesnotexist:v9.9")


def test_analyze_hub_server_error():
    mock_response = MagicMock()
    mock_response.status_code = 500
    error = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=mock_response
    )

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = error
        with pytest.raises(RuntimeError, match="500"):
            image_analyzer.analyze("nginx:latest")


def test_analyze_network_timeout():
    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = (
            httpx.ConnectTimeout("timeout")
        )
        with pytest.raises(RuntimeError, match="Failed to reach Docker Hub"):
            image_analyzer.analyze("nginx:latest")
