from datetime import UTC, datetime

import pytest

Image = pytest.importorskip("PIL.Image")

from vinculo_frame.gallery.controller import PhotoSlide, UnavailableSlide, WelcomeSlide  # noqa: E402
from vinculo_frame.gallery.render import BACKGROUND_BOTTOM, Renderer  # noqa: E402

NOW = datetime(2026, 5, 1, 13, 0, tzinfo=UTC)
SIZES = [(1920, 1080), (1080, 1920), (800, 480), (1024, 600)]
RED = (220, 30, 30)


@pytest.fixture
def renderer():
    return Renderer()


def light_pixels(image, box):
    """Píxeles claros (texto crema) dentro de ``box``."""
    grey = image.crop(box).convert("L")
    return sum(grey.histogram()[180:])


def is_reddish(pixel):
    r, g, b = pixel
    return r > 180 and g < 80 and b < 80


@pytest.mark.parametrize("size", SIZES)
def test_photo_fills_screen_and_stays_centered(renderer, make_photo, size):
    photo_image = Image.new("RGB", (400, 300), RED)
    out = renderer.render(PhotoSlide(make_photo(1), photo_image), size, NOW)
    assert out.size == size and out.mode == "RGB"
    assert is_reddish(out.getpixel((size[0] // 2, size[1] // 2)))


def test_portrait_photo_on_landscape_screen_has_soft_sides(renderer, make_photo):
    photo_image = Image.new("RGB", (300, 400), RED)
    out = renderer.render(PhotoSlide(make_photo(1), photo_image), (1920, 1080), NOW)
    side = out.getpixel((40, 300))
    # Los laterales son la misma foto desenfocada y oscurecida, no negro ni la foto tal cual.
    assert side != (0, 0, 0) and not is_reddish(side) and side[0] > side[1]


def test_caption_area_has_text(renderer, make_photo):
    photo_image = Image.new("RGB", (1600, 900), (90, 90, 90))
    with_name = renderer.render(PhotoSlide(make_photo(1), photo_image), (1600, 900), NOW)
    no_name = renderer.render(PhotoSlide(make_photo(1, sender=""), photo_image), (1600, 900), NOW)
    band = (0, 600, 1600, 900)
    assert light_pixels(with_name, band) > light_pixels(no_name, band) > 0


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("kind", ["welcome", "unavailable"])
def test_message_screens(renderer, make_photo, size, kind):
    slide = WelcomeSlide() if kind == "welcome" else UnavailableSlide(make_photo(1))
    out = renderer.render(slide, size, NOW)
    assert out.size == size
    # Tiene texto claro en el centro y nada en el borde superior.
    assert light_pixels(out, (0, size[1] // 3, size[0], 2 * size[1] // 3)) > 0
    assert light_pixels(out, (0, 0, size[0], 8)) == 0


def test_very_long_name_is_shortened(renderer, make_photo):
    photo = make_photo(1, sender="Nombre " * 30)
    out = renderer.render(PhotoSlide(photo, Image.new("RGB", (10, 10))), (800, 480), NOW)
    assert out.size == (800, 480)


def test_blank_is_plain_background(renderer):
    assert renderer.blank((100, 50)).getpixel((5, 5)) == BACKGROUND_BOTTOM


def test_unknown_slide_raises(renderer):
    with pytest.raises(TypeError):
        renderer.render("no es una diapositiva", (100, 100), NOW)
