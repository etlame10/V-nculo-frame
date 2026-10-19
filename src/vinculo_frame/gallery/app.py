"""Ensamblaje de la galería a partir de la configuración y del almacenamiento local."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import Settings
from ..storage import LocalStore
from .controller import GalleryController, Slide
from .imaging import make_loader
from .layout import Size
from .render import Renderer


def build_controller(settings: Settings, store: LocalStore, screen: Size) -> GalleryController:
    return GalleryController(
        source=store.list_photos,
        loader=make_loader(settings.photos_dir, screen),
        slide_seconds=settings.slide_seconds,
    )


def run_gallery(
    settings: Settings,
    size: Size | None,
    fullscreen: bool,
    max_seconds: float | None = None,
    screenshot: str | None = None,
) -> None:
    # Importación diferida: pygame solo hace falta para mostrar la ventana.
    from .display import GalleryWindow

    settings.photos_dir.mkdir(parents=True, exist_ok=True)
    with LocalStore(settings.database_path) as store:
        window = GalleryWindow(Renderer(), size=size, fullscreen=fullscreen)
        window.run(
            lambda screen: build_controller(settings, store, screen),
            max_seconds=max_seconds,
            screenshot=screenshot,
        )


def render_previews(
    settings: Settings,
    out_dir: Path,
    size: Size,
    count: int,
    now: datetime,
) -> list[Path]:
    """Dibuja las ``count`` primeras diapositivas como PNG, sin pantalla."""
    out_dir.mkdir(parents=True, exist_ok=True)
    renderer = Renderer()
    paths: list[Path] = []
    with LocalStore(settings.database_path) as store:
        controller = build_controller(settings, store, size)
        slide: Slide | None = controller.tick(0.0)
        for i in range(count):
            slide = slide or controller.current
            assert slide is not None
            path = out_dir / f"diapositiva-{i + 1:02d}.png"
            renderer.render(slide, size, now).save(path)
            paths.append(path)
            slide = controller.skip(float(i + 1))
    return paths
