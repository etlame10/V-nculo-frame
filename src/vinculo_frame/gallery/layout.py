"""Cálculos de tamaño y posición (lógica pura).

Todas las medidas dependen del lado corto de la pantalla, de modo que la
proporción es la misma en una pantalla de 800×480, en una de 1920×1080 o
en una vertical.
"""

from __future__ import annotations

from dataclasses import dataclass

Size = tuple[int, int]


def parse_size(text: str) -> Size:
    """``"1920x1080"`` → ``(1920, 1080)``."""
    try:
        w, h = (int(v) for v in text.lower().split("x"))
    except ValueError as exc:
        raise ValueError(f"tamaño no válido {text!r}; usa ANCHOxALTO, p. ej. 1920x1080") from exc
    if not (100 <= w <= 10000 and 100 <= h <= 10000):
        raise ValueError(f"tamaño fuera de rango: {text!r}")
    return w, h


def contain(src: Size, box: Size) -> Size:
    """Tamaño máximo que cabe entero en ``box`` sin deformar."""
    scale = min(box[0] / src[0], box[1] / src[1])
    return max(1, round(src[0] * scale)), max(1, round(src[1] * scale))


def cover(src: Size, box: Size) -> Size:
    """Tamaño mínimo que llena ``box`` por completo sin deformar."""
    scale = max(box[0] / src[0], box[1] / src[1])
    return max(1, round(src[0] * scale)), max(1, round(src[1] * scale))


def centered(inner: Size, box: Size) -> tuple[int, int]:
    return (box[0] - inner[0]) // 2, (box[1] - inner[1]) // 2


@dataclass(frozen=True)
class Metrics:
    margin: int
    title_px: int  # remitente y títulos
    body_px: int  # fecha y textos secundarios
    band_height: int  # degradado inferior que hace legible el texto sobre la foto


def metrics(screen: Size) -> Metrics:
    short = min(screen)
    # Tamaños mínimos pensados para leer a 2-3 m en una pantalla pequeña.
    title = max(28, round(short * 0.07))
    body = max(22, round(short * 0.05))
    margin = max(16, round(short * 0.045))
    band = margin * 2 + title + body + round(body * 0.6)
    return Metrics(
        margin=margin,
        title_px=title,
        body_px=body,
        band_height=min(band, screen[1] // 2),
    )
