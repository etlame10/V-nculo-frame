"""Lectura de fotografías del disco local con Pillow.

Cada lectura comprueba de nuevo el archivo: un fichero que pasó la
validación al recibirse puede haberse dañado después (tarjeta SD, corte de
luz). Todos los fallos se convierten en ``PhotoLoadError``.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageOps

from ..storage import Photo
from .layout import Size

# Mismos formatos que acepta media.py.
FORMATS = ("JPEG", "PNG", "WEBP")
# 40 megapíxeles: más que cualquier móvil actual y lejos de las "bombas de descompresión".
MAX_PIXELS = 40_000_000


class PhotoLoadError(Exception):
    """La foto no se puede leer o no es una imagen válida."""


def photo_path(photos_dir: Path, photo: Photo) -> Path:
    """Ruta del archivo de ``photo``. Rechaza nombres que intenten salir de la carpeta."""
    name = photo.file_name
    if not name or name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise PhotoLoadError(f"nombre de archivo no válido: {name!r}")
    return photos_dir / name


def load_image(path: Path, max_size: Size, max_pixels: int = MAX_PIXELS) -> Image.Image:
    """Abre ``path`` y devuelve una imagen RGB orientada que cabe en ``max_size``."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path, formats=FORMATS) as im:
                if im.width * im.height > max_pixels:
                    raise PhotoLoadError(f"imagen demasiado grande ({im.width}×{im.height})")
                # La orientación EXIF puede girar la foto: reservar el lado largo en ambos ejes.
                longest = max(max_size)
                # Para JPEG, decodifica directamente a menor resolución (mucho más rápido en la Pi).
                im.draft("RGB", (longest, longest))
                im.load()
                image = ImageOps.exif_transpose(im)
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        return image
    except PhotoLoadError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        # OSError incluye archivo inexistente, sin permisos, truncado o no reconocido.
        raise PhotoLoadError(str(exc) or type(exc).__name__) from exc
    except Image.DecompressionBombWarning as exc:
        raise PhotoLoadError("imagen demasiado grande") from exc


def make_loader(photos_dir: Path, screen: Size) -> Callable[[Photo], Image.Image]:
    """Cargador para ``GalleryController``: lee la foto al tamaño de la pantalla."""

    def load(photo: Photo) -> Image.Image:
        return load_image(photo_path(photos_dir, photo), screen)

    return load
