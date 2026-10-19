import io
from dataclasses import replace

import pytest

Image = pytest.importorskip("PIL.Image")

from vinculo_frame.gallery.imaging import (  # noqa: E402
    PhotoLoadError,
    load_image,
    make_loader,
    photo_path,
)


def write(path, size=(400, 300), fmt="JPEG", mode="RGB", exif_orientation=None):
    image = Image.new(mode, size, (200, 100, 50) if mode == "RGB" else None)
    kwargs = {}
    if exif_orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs["exif"] = exif
    image.save(path, fmt, **kwargs)
    return path


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_loads_supported_formats_as_rgb(tmp_path, fmt):
    image = load_image(write(tmp_path / "a", fmt=fmt), (1920, 1080))
    assert image.mode == "RGB"
    assert image.size == (400, 300)  # nunca se amplía


def test_downscales_to_screen(tmp_path):
    image = load_image(write(tmp_path / "big.jpg", size=(4000, 3000)), (800, 480))
    assert image.size == (640, 480)


def test_applies_exif_orientation(tmp_path):
    # Orientación 6 = girar 90°: una foto guardada en horizontal se ve vertical.
    path = write(tmp_path / "rotated.jpg", size=(400, 300), exif_orientation=6)
    assert load_image(path, (1920, 1080)).size == (300, 400)


def test_converts_transparent_png(tmp_path):
    path = write(tmp_path / "t.png", fmt="PNG", mode="RGBA")
    assert load_image(path, (100, 100)).mode == "RGB"


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"\xff\xd8\xff\xe0" + b"\x42" * 500,  # cabecera JPEG, contenido dañado
        b"GIF89a" + b"\x00" * 100,  # formato no admitido
    ],
)
def test_broken_files_raise_load_error(tmp_path, content):
    path = tmp_path / "bad.jpg"
    path.write_bytes(content)
    with pytest.raises(PhotoLoadError):
        load_image(path, (100, 100))


def test_truncated_jpeg_raises_load_error(tmp_path):
    buffer = io.BytesIO()
    Image.new("RGB", (800, 600), (10, 20, 30)).save(buffer, "JPEG")
    path = tmp_path / "cut.jpg"
    path.write_bytes(buffer.getvalue()[: len(buffer.getvalue()) // 3])
    with pytest.raises(PhotoLoadError):
        load_image(path, (100, 100))


def test_missing_file_raises_load_error(tmp_path):
    with pytest.raises(PhotoLoadError):
        load_image(tmp_path / "no-existe.jpg", (100, 100))


def test_too_many_pixels_rejected(tmp_path):
    path = write(tmp_path / "huge.png", size=(300, 300), fmt="PNG")
    with pytest.raises(PhotoLoadError):
        load_image(path, (100, 100), max_pixels=300 * 300 - 1)


@pytest.mark.parametrize("name", ["", "..", "../secreto.jpg", "a/b.jpg", "a\\b.jpg", "a\x00.jpg"])
def test_photo_path_rejects_escaping_names(tmp_path, make_photo, name):
    photo = replace(make_photo(1), file_name=name)
    with pytest.raises(PhotoLoadError):
        photo_path(tmp_path, photo)


def test_make_loader_reads_from_photos_dir(tmp_path, make_photo):
    photo = make_photo(1, file_name="foto.jpg")
    write(tmp_path / "foto.jpg", size=(2000, 1000))
    assert make_loader(tmp_path, (1000, 1000))(photo).size == (1000, 500)
