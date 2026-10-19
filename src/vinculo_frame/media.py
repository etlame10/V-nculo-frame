"""Validación y guardado local de fotografías recibidas.

Las fotografías llegan de fuentes externas (Telegram, panel web), así que no
nos fiamos de su nombre ni del tipo MIME declarado: se comprueba el tamaño y
la firma real de los bytes. El nombre del archivo en disco se deriva del hash
SHA-256 del contenido, nunca de datos del remitente, lo que evita rutas
maliciosas y duplicados.

Esta validación es una primera barrera. La decodificación completa (y la
eliminación de metadatos EXIF como la ubicación) se añadirá en la fase 2
con una librería de imagen.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


class PhotoRejected(ValueError):
    """La fotografía no cumple los requisitos y no se guarda."""


@dataclass(frozen=True)
class ImageType:
    mime: str
    extension: str


JPEG = ImageType("image/jpeg", ".jpg")
PNG = ImageType("image/png", ".png")
WEBP = ImageType("image/webp", ".webp")


@dataclass(frozen=True)
class SavedPhoto:
    path: Path
    sha256: str
    image_type: ImageType
    size_bytes: int


def detect_image_type(data: bytes) -> ImageType:
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return WEBP
    raise PhotoRejected("formato no admitido (solo JPEG, PNG o WebP)")


def validate_photo(data: bytes, max_bytes: int) -> ImageType:
    if not data:
        raise PhotoRejected("archivo vacío")
    if len(data) > max_bytes:
        raise PhotoRejected(f"archivo demasiado grande ({len(data)} > {max_bytes} bytes)")
    return detect_image_type(data)


def save_photo(photos_dir: Path, data: bytes, max_bytes: int) -> SavedPhoto:
    """Valida y guarda ``data`` de forma atómica. Es idempotente por contenido."""
    image_type = validate_photo(data, max_bytes)
    digest = hashlib.sha256(data).hexdigest()
    photos_dir.mkdir(parents=True, exist_ok=True)
    target = photos_dir / f"{digest}{image_type.extension}"

    if not target.exists():
        # Escribir en temporal y renombrar: un corte de luz no deja archivos a medias.
        fd, tmp_name = tempfile.mkstemp(dir=photos_dir, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(data)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, target)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    return SavedPhoto(target, digest, image_type, len(data))
