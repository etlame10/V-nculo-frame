import os

import pytest

pytest.importorskip("PIL")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # sin pantalla física
pygame = pytest.importorskip("pygame")

from vinculo_frame.gallery.controller import GalleryController  # noqa: E402
from vinculo_frame.gallery.display import GalleryWindow  # noqa: E402
from vinculo_frame.gallery.render import Renderer  # noqa: E402


class FakeClock:
    def __init__(self, step):
        self.now = 0.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


def run_window(tmp_path, controller, renderer=None, seconds=3.0):
    shot = tmp_path / "shot.png"
    window = GalleryWindow(
        renderer or Renderer(), size=(640, 360), fullscreen=False, clock=FakeClock(0.5)
    )
    window.run(lambda size: controller, max_seconds=seconds, screenshot=str(shot))
    return pygame.image.load(str(shot)) if shot.exists() else None


def test_window_shows_welcome_without_photos(tmp_path):
    controller = GalleryController(list, lambda p: p, slide_seconds=5)
    shot = run_window(tmp_path, controller)
    assert shot.get_size() == (640, 360)


def test_window_survives_render_errors(tmp_path):
    class BrokenRenderer(Renderer):
        def render(self, slide, size, now):
            raise RuntimeError("fallo de dibujo")

    controller = GalleryController(list, lambda p: p, slide_seconds=5)
    shot = run_window(tmp_path, controller, BrokenRenderer())
    assert shot is not None  # muestra el fondo liso en lugar de cerrarse


def test_controller_receives_real_window_size():
    seen = []

    def make(size):
        seen.append(size)
        return GalleryController(list, lambda p: p)

    GalleryWindow(Renderer(), size=(500, 300), fullscreen=False, clock=FakeClock(1)).run(
        make, max_seconds=1
    )
    assert seen == [(500, 300)]


def test_escape_key_closes():
    controller = GalleryController(list, lambda p: p)
    window = GalleryWindow(Renderer(), size=(320, 200), fullscreen=False, clock=FakeClock(1))

    def make(size):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        return controller

    window.run(make, max_seconds=None)  # sin límite: solo termina por la tecla
