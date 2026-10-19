"""Composición de cada diapositiva como imagen (Pillow).

Produce una imagen RGB del tamaño exacto de la pantalla. No usa pygame, así
que se puede probar y previsualizar sin pantalla física.

Estilo: la foto ocupa todo lo posible; el espacio sobrante se rellena con
la misma foto desenfocada y oscurecida (sin franjas negras). El remitente y
la fecha van abajo, sobre un degradado suave. Colores cálidos, texto grande.
"""

from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import captions
from .controller import PhotoSlide, Slide, UnavailableSlide, WelcomeSlide
from .layout import Metrics, Size, centered, contain, cover, metrics

log = logging.getLogger(__name__)

BACKGROUND_TOP = (58, 46, 39)  # marrón cálido
BACKGROUND_BOTTOM = (36, 28, 24)
TEXT = (255, 246, 236)  # crema
TEXT_SOFT = (232, 214, 196)
ACCENT = (242, 184, 128)  # melocotón

# DejaVu viene con Raspberry Pi OS (paquete fonts-dejavu-core) y cubre tildes y eñes.
FONT_DIRS = (Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu"))
FONT_REGULAR = "DejaVuSans.ttf"
FONT_BOLD = "DejaVuSans-Bold.ttf"

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


@lru_cache(maxsize=32)
def _font(name: str, size: int) -> Font:
    for folder in FONT_DIRS:
        path = folder / name
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    log.warning("fuente %s no encontrada; se usa la de Pillow", name)
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Font, width: int) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        candidate = f"{lines[-1]} {word}" if lines else word
        if lines and draw.textlength(candidate, font=font) <= width:
            lines[-1] = candidate
        else:
            lines.append(word)
    return lines


def _gradient_background(size: Size) -> Image.Image:
    top = Image.new("RGB", size, BACKGROUND_TOP)
    bottom = Image.new("RGB", size, BACKGROUND_BOTTOM)
    mask = Image.linear_gradient("L").resize(size)
    return Image.composite(bottom, top, mask)


def _blurred_fill(image: Image.Image, size: Size) -> Image.Image:
    # Desenfocar una miniatura es mucho más barato que desenfocar a pantalla completa.
    small = image.copy()
    small.thumbnail((64, 64))
    small = small.filter(ImageFilter.GaussianBlur(3))
    filled = small.resize(cover(small.size, size), Image.Resampling.BILINEAR)
    filled = filled.crop((*centered(size, filled.size), *_corner(size, filled.size)))
    return ImageEnhance.Brightness(filled).enhance(0.45)


def _corner(inner: Size, outer: Size) -> tuple[int, int]:
    x, y = centered(inner, outer)
    return x + inner[0], y + inner[1]


def _bottom_shade(canvas: Image.Image, m: Metrics) -> None:
    w, h = canvas.size
    band = m.band_height
    alpha = Image.linear_gradient("L").resize((w, band)).point(lambda v: v * 0.7)
    shade = Image.new("RGB", (w, band), (20, 14, 10))
    canvas.paste(shade, (0, h - band), alpha)


class Renderer:
    def render(self, slide: Slide, size: Size, now: datetime) -> Image.Image:
        """``now`` con zona horaria local; se usa para "Hoy"/"Ayer"."""
        match slide:
            case PhotoSlide(photo, image):
                return self._photo(image, captions.caption_for(photo, now), size)
            case UnavailableSlide(photo):
                detail = captions.one_line(captions.caption_for(photo, now))
                return self._message(
                    size, captions.UNAVAILABLE_TITLE, detail, captions.UNAVAILABLE_BODY
                )
            case WelcomeSlide():
                return self._message(size, captions.WELCOME_TITLE, captions.WELCOME_BODY)
        raise TypeError(f"diapositiva desconocida: {slide!r}")

    def blank(self, size: Size) -> Image.Image:
        """Último recurso si el dibujo falla: fondo liso, sin texto."""
        return Image.new("RGB", size, BACKGROUND_BOTTOM)

    def _photo(self, image: Image.Image, caption: captions.Caption, size: Size) -> Image.Image:
        m = metrics(size)
        canvas = _blurred_fill(image, size)
        fitted = image.resize(contain(image.size, size), Image.Resampling.LANCZOS)
        canvas.paste(fitted, centered(fitted.size, size))
        _bottom_shade(canvas, m)

        draw = ImageDraw.Draw(canvas)
        width = size[0] - 2 * m.margin
        y = size[1] - m.margin
        date_font = _font(FONT_REGULAR, m.body_px)
        y -= m.body_px
        draw.text((m.margin, y), _fit(draw, caption.when, date_font, width), TEXT_SOFT, date_font)
        if caption.sender:
            name_font = _font(FONT_BOLD, m.title_px)
            y -= round(m.title_px * 1.2)
            draw.text((m.margin, y), _fit(draw, caption.sender, name_font, width), TEXT, name_font)
        return canvas

    def _message(self, size: Size, title: str, *paragraphs: str) -> Image.Image:
        m = metrics(size)
        canvas = _gradient_background(size)
        draw = ImageDraw.Draw(canvas)
        width = round(size[0] * 0.8)
        title_font = _font(FONT_BOLD, round(m.title_px * 1.15))
        body_font = _font(FONT_REGULAR, m.body_px)

        blocks: list[tuple[list[str], Font, tuple[int, int, int], int]] = [
            (_wrap(draw, title, title_font, width), title_font, TEXT, round(m.title_px * 1.4))
        ]
        for i, text in enumerate(paragraphs):
            colour = ACCENT if i == 0 and len(paragraphs) > 1 else TEXT_SOFT
            blocks.append((_wrap(draw, text, body_font, width), body_font, colour, m.body_px * 1.4))

        gap = m.margin
        total = sum(len(lines) * step for lines, _, _, step in blocks) + gap * (len(blocks) - 1)
        y = (size[1] - total) / 2
        for lines, font, colour, step in blocks:
            for line in lines:
                draw.text((size[0] / 2, y), line, colour, font, anchor="ma")
                y += step
            y += gap
        return canvas


def _fit(draw: ImageDraw.ImageDraw, text: str, font: Font, width: int) -> str:
    """Acorta con "…" si el texto no cabe en una línea."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"
