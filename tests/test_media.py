import hashlib

import pytest

from vinculo_frame.media import JPEG, PNG, WEBP, PhotoRejected, save_photo, validate_photo

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 100
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 100


@pytest.mark.parametrize(
    ("data", "expected"), [(JPEG_BYTES, JPEG), (PNG_BYTES, PNG), (WEBP_BYTES, WEBP)]
)
def test_accepts_supported_formats(data, expected):
    assert validate_photo(data, max_bytes=1000) == expected


@pytest.mark.parametrize(
    "data",
    [b"", b"GIF89a" + b"\x00" * 10, b"<html>", b"%PDF-1.7", b"RIFF\x00\x00\x00\x00WAVE"],
)
def test_rejects_empty_or_unsupported(data):
    with pytest.raises(PhotoRejected):
        validate_photo(data, max_bytes=1000)


def test_rejects_oversized():
    with pytest.raises(PhotoRejected):
        validate_photo(JPEG_BYTES, max_bytes=10)


def test_save_uses_content_hash_and_is_idempotent(tmp_path):
    saved = save_photo(tmp_path / "photos", JPEG_BYTES, max_bytes=1000)
    digest = hashlib.sha256(JPEG_BYTES).hexdigest()
    assert saved.path == tmp_path / "photos" / f"{digest}.jpg"
    assert saved.path.read_bytes() == JPEG_BYTES
    assert save_photo(tmp_path / "photos", JPEG_BYTES, max_bytes=1000) == saved
    assert [p.name for p in (tmp_path / "photos").iterdir()] == [saved.path.name]


def test_rejected_photo_leaves_no_file(tmp_path):
    with pytest.raises(PhotoRejected):
        save_photo(tmp_path / "photos", b"no es una imagen", max_bytes=1000)
    assert not (tmp_path / "photos").exists()
