"""Images in a form the model accepts: bounded size, flat colour, PNG (JPEG when too heavy)."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

from ddk.adapters.screenshot_diff_local import flatten_to_rgb

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
MAX_EDGE = 1568
MAX_BYTES = 3_500_000
_JPEG_QUALITIES = (85, 70, 50)
_UNREADABLE = (OSError, ValueError, SyntaxError, Image.DecompressionBombError)


def encode_for_model(
    path: str | Path | None, *, max_edge: int = MAX_EDGE, max_bytes: int = MAX_BYTES
) -> tuple[str, str] | None:
    """``(base64, media_type)`` of the image, or ``None`` when it cannot be read."""
    if not path:
        return None
    try:
        with Image.open(path) as image:
            picture = flatten_to_rgb(image)
        picture.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        data, media_type = _smallest_fit(picture, max_bytes)
    except _UNREADABLE:
        return None
    return base64.b64encode(data).decode("ascii"), media_type


def is_decodable(path: str | Path) -> bool:
    """Whether Pillow can fully decode the file as an image."""
    try:
        with Image.open(path) as image:
            image.load()
    except _UNREADABLE:
        return False
    return True


def _smallest_fit(picture: Image.Image, max_bytes: int) -> tuple[bytes, str]:
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    if buffer.tell() <= max_bytes:
        return buffer.getvalue(), "image/png"
    data = b""
    for quality in _JPEG_QUALITIES:
        buffer = io.BytesIO()
        picture.save(buffer, format="JPEG", quality=quality)
        data = buffer.getvalue()
        if len(data) <= max_bytes:
            break
    return data, "image/jpeg"


def encode_design_image(path: str | Path) -> tuple[str, str]:
    """Like ``encode_for_model``, but a file Pillow cannot decode is sent unchanged."""
    encoded = encode_for_model(path)
    if encoded is not None:
        return encoded
    location = Path(path)
    media_type = _MEDIA_TYPES.get(location.suffix.lower(), "image/png")
    return base64.b64encode(location.read_bytes()).decode("ascii"), media_type
