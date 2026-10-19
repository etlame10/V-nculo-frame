"""Ventana de la galería con pygame.

Es una capa fina: pregunta al controlador qué mostrar, lo dibuja con
``Renderer`` y lo copia en pantalla. Teclas para desarrollo: Esc o Q para
salir, flecha derecha o espacio para pasar de foto.

En Raspberry Pi OS con escritorio, SDL usa Wayland/X11. Sin escritorio
puede usar KMS/DRM (``SDL_VIDEODRIVER=kmsdrm``). Ninguno de los dos casos se
ha probado todavía en una Pi real.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime

import pygame

from .controller import GalleryController, Slide
from .layout import Size
from .render import Renderer

log = logging.getLogger(__name__)

FPS = 4  # suficiente para una galería; consume poca CPU en la Pi


def _local_now() -> datetime:
    return datetime.now().astimezone()


class GalleryWindow:
    def __init__(
        self,
        renderer: Renderer,
        size: Size | None = None,
        fullscreen: bool = True,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = _local_now,
    ) -> None:
        self._controller: GalleryController | None = None
        self._renderer = renderer
        self._requested_size = size
        self._fullscreen = fullscreen
        self._clock = clock
        self._wall_clock = wall_clock
        self._frame: pygame.Surface | None = None

    def open(self) -> Size:
        """Abre la ventana y devuelve su tamaño real."""
        pygame.display.init()
        pygame.display.set_caption("Vínculo Frame")
        if self._fullscreen:
            # (0, 0) = resolución actual de la pantalla.
            screen = pygame.display.set_mode(self._requested_size or (0, 0), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
        else:
            screen = pygame.display.set_mode(self._requested_size or (1280, 720), pygame.RESIZABLE)
        return screen.get_size()

    def run(
        self,
        make_controller: Callable[[Size], GalleryController],
        max_seconds: float | None = None,
        screenshot: str | None = None,
    ) -> None:
        """Bucle principal.

        ``make_controller`` recibe el tamaño real de la pantalla (para leer las
        fotos a esa resolución). ``max_seconds`` limita la duración y
        ``screenshot`` guarda la última imagen mostrada; ambos sirven para
        pruebas y demostraciones sin pantalla.
        """
        self._controller = make_controller(self.open())
        started = self._clock()
        ticker = pygame.time.Clock()
        try:
            while self._handle_events():
                now = self._clock()
                slide = self._controller.tick(now)
                if slide is not None or self._frame is None:
                    self._draw(slide or self._controller.current)
                self._present()
                if max_seconds is not None and now - started >= max_seconds:
                    break
                ticker.tick(FPS)
            if screenshot is not None:
                pygame.image.save(pygame.display.get_surface(), screenshot)
        finally:
            pygame.display.quit()

    def _handle_events(self) -> bool:
        assert self._controller is not None
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    return False
                if event.key in (pygame.K_RIGHT, pygame.K_SPACE):
                    self._draw(self._controller.skip(self._clock()) or self._controller.current)
            elif event.type == pygame.WINDOWSIZECHANGED:
                self._draw(self._controller.current)
        return True

    def _draw(self, slide: Slide | None) -> None:
        size = pygame.display.get_surface().get_size()
        try:
            image = (
                self._renderer.render(slide, size, self._wall_clock())
                if slide is not None
                else self._renderer.blank(size)
            )
        except Exception:
            # Un fallo de dibujo no debe cerrar la galería; la siguiente foto lo reintenta.
            log.exception("no se ha podido dibujar la diapositiva")
            image = self._renderer.blank(size)
        self._frame = pygame.image.frombytes(image.tobytes(), image.size, "RGB")

    def _present(self) -> None:
        screen = pygame.display.get_surface()
        if self._frame is not None:
            screen.blit(self._frame, (0, 0))
        pygame.display.flip()
