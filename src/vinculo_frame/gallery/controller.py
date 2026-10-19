"""Qué se muestra en pantalla y cuándo (lógica pura).

El controlador no sabe dibujar ni leer archivos: recibe una función que
devuelve las fotos del almacenamiento local y otra que carga la imagen de
una foto. Cualquier error de esas funciones se registra y se convierte en
una pantalla comprensible; nunca detiene la galería.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..storage import Photo
from .playlist import Playlist

log = logging.getLogger(__name__)

# Un aviso de error se lee en pocos segundos; no hace falta el intervalo completo.
UNAVAILABLE_SECONDS = 8.0


@dataclass(frozen=True)
class WelcomeSlide:
    """No hay fotos todavía."""


@dataclass(frozen=True)
class PhotoSlide:
    photo: Photo
    image: Any = field(compare=False, repr=False)


@dataclass(frozen=True)
class UnavailableSlide:
    """La foto existe pero no se ha podido leer."""

    photo: Photo


Slide = WelcomeSlide | PhotoSlide | UnavailableSlide


class GalleryController:
    def __init__(
        self,
        source: Callable[[], Sequence[Photo]],
        loader: Callable[[Photo], Any],
        slide_seconds: float = 15.0,
        refresh_seconds: float = 30.0,
        playlist: Playlist | None = None,
    ) -> None:
        if slide_seconds <= 0 or refresh_seconds <= 0:
            raise ValueError("los intervalos deben ser positivos")
        self._source = source
        self._loader = loader
        self._slide_seconds = slide_seconds
        self._refresh_seconds = refresh_seconds
        self._playlist = playlist or Playlist()
        self._current: Slide | None = None
        self._change_at = float("-inf")
        self._refresh_at = float("-inf")

    @property
    def current(self) -> Slide | None:
        return self._current

    def tick(self, now: float) -> Slide | None:
        """Llamar con frecuencia. Devuelve la nueva diapositiva si ha cambiado."""
        new_photos = 0
        if now >= self._refresh_at:
            new_photos = self._refresh(now)

        due = now >= self._change_at
        waiting = isinstance(self._current, WelcomeSlide) and len(self._playlist) > 0
        if self._current is None or due or waiting or new_photos:
            return self._advance(now)
        return None

    def skip(self, now: float) -> Slide | None:
        """Pasar a la siguiente foto ya (teclado en desarrollo; botón en el futuro)."""
        return self._advance(now)

    def _refresh(self, now: float) -> int:
        self._refresh_at = now + self._refresh_seconds
        try:
            photos = self._source()
        except Exception:
            # Base de datos bloqueada o dañada: seguimos con las fotos que ya teníamos.
            log.exception("no se ha podido leer la lista de fotos; se reintentará")
            return 0
        return self._playlist.update(photos)

    def _advance(self, now: float) -> Slide | None:
        photo = self._playlist.next(now)
        if photo is None:
            return self._show(WelcomeSlide(), now, self._slide_seconds)

        current = self._current
        if isinstance(current, PhotoSlide) and current.photo == photo:
            # Única foto disponible: no hace falta volver a leerla ni redibujar.
            self._change_at = now + self._slide_seconds
            return None

        try:
            image = self._loader(photo)
        except Exception as exc:
            log.warning("no se puede mostrar la foto %s: %s", photo.id, exc)
            self._playlist.mark_failed(photo.id, now)
            slide: Slide = UnavailableSlide(photo)
            return self._show(slide, now, min(self._slide_seconds, UNAVAILABLE_SECONDS))
        return self._show(PhotoSlide(photo, image), now, self._slide_seconds)

    def _show(self, slide: Slide, now: float, seconds: float) -> Slide | None:
        self._change_at = now + seconds
        if slide == self._current:
            return None
        self._current = slide
        return slide
