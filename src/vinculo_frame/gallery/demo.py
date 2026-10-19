"""Fotografías ficticias para probar la galería sin fotos reales.

Genera paisajes sintéticos (degradados y formas) en distintas proporciones
y los registra en el almacenamiento local con remitentes inventados,
usando el mismo camino que usará la recepción real: ``media.save_photo``
y ``LocalStore.add_photo``.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from ..media import save_photo
from ..storage import LocalStore, Photo

DEMO_SENDER_PREFIX = "demo-"

# (remitente, tamaño, cielo, suelo, sol); proporciones variadas a propósito.
_SCENES = (
    ("Ana", (1600, 1200), (250, 190, 140), (120, 150, 90), (255, 230, 170)),
    ("Luis", (1080, 1440), (140, 180, 230), (70, 110, 80), (255, 250, 220)),
    ("Marta", (1920, 1080), (230, 140, 120), (90, 70, 110), (255, 210, 150)),
    ("", (1200, 1200), (180, 210, 220), (200, 180, 140), (255, 255, 240)),
    (
        "Carmen María de los Ángeles Fernández",
        (2400, 1000),
        (120, 90, 160),
        (40, 60, 70),
        (250, 200, 120),
    ),
    ("Pablo", (900, 1600), (250, 220, 180), (150, 120, 90), (255, 240, 200)),
)


def _scene(size: tuple[int, int], sky, ground, sun, index: int) -> bytes:
    w, h = size
    image = Image.new("RGB", size, sky)
    draw = ImageDraw.Draw(image)
    horizon = round(h * 0.62)
    for y in range(horizon):
        t = y / horizon
        draw.line([(0, y), (w, y)], tuple(round(c * (0.75 + 0.25 * t)) for c in sky))
    r = min(w, h) // 8
    cx, cy = w * (0.25 + 0.1 * index) % w, h * 0.3
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=sun)
    draw.polygon([(0, horizon), (w * 0.35, h * 0.45), (w * 0.7, horizon)], fill=ground)
    draw.rectangle((0, horizon, w, h), fill=tuple(round(c * 0.8) for c in ground))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def _broken_jpeg() -> bytes:
    """Cabecera JPEG válida (pasa ``media.validate_photo``) pero contenido dañado."""
    return b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF\x00" + b"\x42" * 2048


def create_demo_photos(
    store: LocalStore,
    photos_dir: Path,
    now: datetime,
    count: int = len(_SCENES),
    with_broken: bool = False,
    max_bytes: int = 10 * 1024 * 1024,
) -> list[Photo]:
    """Crea hasta ``count`` fotos ficticias (una por día hacia atrás desde ``now``)."""
    if not 1 <= count <= len(_SCENES):
        raise ValueError(f"count debe estar entre 1 y {len(_SCENES)}")

    items = [
        (name, _scene(size, sky, ground, sun, i))
        for i, (name, size, sky, ground, sun) in enumerate(_SCENES[:count])
    ]
    if with_broken:
        items.append(("Jorge", _broken_jpeg()))

    created = []
    for days_ago, (name, data) in enumerate(items):
        saved = save_photo(photos_dir, data, max_bytes)
        created.append(
            store.add_photo(
                sha256=saved.sha256,
                file_name=saved.path.name,
                mime=saved.image_type.mime,
                sender_id=f"{DEMO_SENDER_PREFIX}{days_ago}",
                sender_name=name,
                received_at=now - timedelta(days=days_ago, hours=days_ago * 3),
            )
        )
    return created
