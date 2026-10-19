"""Orden de rotación de la galería (lógica pura, sin pantalla ni disco).

Reglas:

* Las fotos se recorren de la más reciente a la más antigua y después se
  vuelve a empezar.
* Una foto que llega mientras la galería está en marcha se muestra la
  siguiente, antes de seguir con la rotación.
* Una foto que no se ha podido leer se salta durante ``retry_after``
  segundos (puede que se esté copiando o que el disco haya fallado un
  momento). Si todas fallan, se siguen intentando en orden para no dejar
  la pantalla congelada.

Los tiempos son monotónicos (segundos), igual que en ``sos.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ..storage import Photo

_SortKey = tuple[datetime, int]


def _key(photo: Photo) -> _SortKey:
    return (photo.received_at, photo.id)


class Playlist:
    def __init__(self, retry_after: float = 300.0) -> None:
        self._retry_after = retry_after
        self._photos: dict[int, Photo] = {}
        self._order: list[Photo] = []  # de la más reciente a la más antigua
        self._known: set[int] | None = None  # None hasta la primera carga
        self._pending: list[int] = []  # fotos nuevas que se muestran antes
        self._failed_until: dict[int, float] = {}
        self._current: Photo | None = None

    def __len__(self) -> int:
        return len(self._order)

    @property
    def current(self) -> Photo | None:
        return self._current

    def update(self, photos: Sequence[Photo]) -> int:
        """Sustituye el conjunto de fotos disponibles. Devuelve cuántas son nuevas."""
        self._photos = {p.id: p for p in photos}
        self._order = sorted(self._photos.values(), key=_key, reverse=True)
        ids = set(self._photos)

        new: list[int] = []
        if self._known is not None:
            new = [p.id for p in self._order if p.id not in self._known]
        self._known = ids if self._known is None else self._known | ids

        self._pending = [i for i in self._pending if i in ids] + new
        self._failed_until = {i: t for i, t in self._failed_until.items() if i in ids}
        return len(new)

    def mark_failed(self, photo_id: int, now: float) -> None:
        self._failed_until[photo_id] = now + self._retry_after

    def next(self, now: float) -> Photo | None:
        """Elige la siguiente foto, o ``None`` si no hay ninguna."""
        if not self._order:
            self._current = None
            return None

        while self._pending:
            photo = self._photos.get(self._pending.pop(0))
            if photo is not None and self._usable(photo, now):
                return self._select(photo)

        candidates = self._rotation()
        photo = next((p for p in candidates if self._usable(p, now)), candidates[0])
        return self._select(photo)

    def _rotation(self) -> list[Photo]:
        """Todas las fotos, empezando por la que sigue a la actual."""
        if self._current is None:
            return list(self._order)
        current = _key(self._current)
        # La siguiente es la primera más antigua que la actual; funciona aunque
        # la actual se haya borrado entretanto.
        start = next((i for i, p in enumerate(self._order) if _key(p) < current), 0)
        return self._order[start:] + self._order[:start]

    def _usable(self, photo: Photo, now: float) -> bool:
        return now >= self._failed_until.get(photo.id, float("-inf"))

    def _select(self, photo: Photo) -> Photo:
        self._current = photo
        return photo
