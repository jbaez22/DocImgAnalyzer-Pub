from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ImageMetadata:
    image: str
    namespace: str
    name: str
    tag: str
    digest: str | None = None
    architecture: str | None = None
    os: str | None = None
    compressed_size_bytes: int | None = None
    layer_count: int | None = None
    last_pushed: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _parse_image_ref(image: str) -> tuple[str, str, str]:
    """
    Parse a Docker image reference into (namespace, name, tag).

    Examples:
        'nginx'               → ('library', 'nginx',  'latest')
        'nginx:1.29-alpine'   → ('library', 'nginx',  '1.29-alpine')
        'user/repo:v1.0'      → ('user',    'repo',   'v1.0')
    """
    tag = "latest"
    # Split tag from the last component only (handles slashes in namespaces)
    last_part = image.split("/")[-1]
    if ":" in last_part:
        tag = last_part.split(":")[-1]
        image = image[: image.rfind(":")]

    if "/" in image:
        namespace, name = image.split("/", 1)
    else:
        namespace, name = "library", image

    return namespace, name, tag


def analyze(image: str) -> ImageMetadata:
    """
    Fetch image metadata from the Docker Hub public API.
    No image is pulled — metadata only.

    Raises:
        ValueError: image not found on Docker Hub (404).
        RuntimeError: upstream API or network error.
    """
    namespace, name, tag = _parse_image_ref(image)
    result = ImageMetadata(image=image, namespace=namespace, name=name, tag=tag)

    url = f"https://hub.docker.com/v2/repositories/{namespace}/{name}/tags/{tag}/"

    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            data: dict = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ValueError(f"Image '{image}' not found on Docker Hub.") from exc
        raise RuntimeError(
            f"Docker Hub API returned {exc.response.status_code} for '{image}'."
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Failed to reach Docker Hub: {exc}") from exc

    result.last_pushed = data.get("last_pushed")
    result.metadata = {
        "full_size_bytes": data.get("full_size"),
        "tag_status": data.get("tag_status"),
        "tag_last_pulled": data.get("tag_last_pulled"),
        "media_type": data.get("media_type"),
    }

    images = data.get("images", [])
    if images:
        # Prefer amd64/linux; fall back to first entry
        img = next((i for i in images if i.get("architecture") == "amd64"), images[0])
        result.architecture = img.get("architecture")
        result.os = img.get("os")
        result.digest = img.get("digest")
        result.compressed_size_bytes = img.get("size")
        result.layer_count = len(img.get("layers", []))

    return result
