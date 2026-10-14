"""encode_for_model / encode_design_image: images in a size and format the model accepts."""

from __future__ import annotations

import base64
import io
import random
from pathlib import Path

import pytest
from PIL import Image

from ddk.services.images import encode_design_image, encode_for_model, is_decodable


def _decode(encoded: tuple[str, str]) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(encoded[0])))


def test_small_png_keeps_its_size_and_pixels(tmp_path: Path) -> None:
    path = tmp_path / "a.png"
    Image.new("RGB", (200, 100), (10, 20, 30)).save(path)

    encoded = encode_for_model(path)

    assert encoded is not None and encoded[1] == "image/png"
    with _decode(encoded) as image:
        assert image.size == (200, 100)
        assert image.convert("RGB").getpixel((5, 5)) == (10, 20, 30)


def test_long_edge_is_limited_and_aspect_ratio_kept(tmp_path: Path) -> None:
    path = tmp_path / "big.png"
    Image.new("RGB", (3000, 1500), (255, 255, 255)).save(path)

    encoded = encode_for_model(path)

    assert encoded is not None
    with _decode(encoded) as image:
        assert max(image.size) <= 1568
        assert abs(image.width / image.height - 2.0) < 0.01


def test_transparency_is_flattened_on_white(tmp_path: Path) -> None:
    path = tmp_path / "t.png"
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(path)

    encoded = encode_for_model(path)

    assert encoded is not None
    with _decode(encoded) as image:
        assert image.convert("RGB").getpixel((0, 0)) == (255, 255, 255)


def test_jpeg_input_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "p.jpg"
    Image.new("RGB", (64, 64), (200, 10, 10)).save(path, quality=90)

    encoded = encode_for_model(path)

    assert encoded is not None


def test_unreadable_or_missing_files_give_none(tmp_path: Path) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")

    assert encode_for_model(broken) is None
    assert encode_for_model(tmp_path / "missing.png") is None
    assert encode_for_model(None) is None


def test_photo_like_image_that_is_too_heavy_as_png_falls_back_to_jpeg(tmp_path: Path) -> None:
    path = tmp_path / "noise.png"
    rng = random.Random(3)
    noise = Image.new("RGB", (1500, 1000))
    noise.putdata(
        [(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(1_500_000)]
    )
    noise.save(path)

    encoded = encode_for_model(path, max_bytes=1_000_000)

    assert encoded is not None
    assert encoded[1] == "image/jpeg"
    assert len(base64.b64decode(encoded[0])) <= 1_000_000


def test_design_image_that_cannot_be_decoded_is_sent_unchanged(tmp_path: Path) -> None:
    raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    png = tmp_path / "stub.png"
    png.write_bytes(raw)
    jpg = tmp_path / "stub.jpg"
    jpg.write_bytes(raw)
    unknown = tmp_path / "stub.bin"
    unknown.write_bytes(raw)

    assert encode_design_image(png) == (base64.b64encode(raw).decode("ascii"), "image/png")
    assert encode_design_image(jpg) == (base64.b64encode(raw).decode("ascii"), "image/jpeg")
    assert encode_design_image(unknown)[1] == "image/png"


def test_design_image_that_can_be_decoded_is_downscaled(tmp_path: Path) -> None:
    path = tmp_path / "big.png"
    Image.new("RGB", (3200, 1600), (255, 255, 255)).save(path)

    encoded = encode_design_image(path)

    with _decode(encoded) as image:
        assert max(image.size) <= 1568


def test_missing_design_image_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        encode_design_image(tmp_path / "missing.png")


def test_is_decodable_accepts_a_real_image(tmp_path: Path) -> None:
    path = tmp_path / "ok.png"
    Image.new("RGB", (32, 32), (1, 2, 3)).save(path)

    assert is_decodable(path)


def test_is_decodable_rejects_broken_files(tmp_path: Path) -> None:
    good = tmp_path / "ok.png"
    Image.new("RGB", (200, 200), (1, 2, 3)).save(good)
    data = good.read_bytes()
    truncated = tmp_path / "truncated.png"
    truncated.write_bytes(data[: len(data) // 2])
    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(data[:60] + b"\xff" * 40 + data[100:])
    garbage = tmp_path / "garbage.png"
    garbage.write_bytes(b"not an image")

    assert not is_decodable(truncated)
    assert not is_decodable(corrupt)
    assert not is_decodable(garbage)
    assert not is_decodable(tmp_path / "missing.png")


def test_corrupt_image_gives_none_instead_of_raising(tmp_path: Path) -> None:
    good = tmp_path / "ok.png"
    Image.new("RGB", (200, 200), (1, 2, 3)).save(good)
    data = good.read_bytes()
    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(data[:60] + b"\xff" * 40 + data[100:])

    assert encode_for_model(corrupt) is None
