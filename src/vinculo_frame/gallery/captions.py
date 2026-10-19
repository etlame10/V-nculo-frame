"""Textos que acompañan a cada foto (lógica pura).

Las fechas se escriben en español sin depender del *locale* del sistema,
que en una Raspberry Pi recién instalada suele ser inglés.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

from ..storage import Photo

MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

MAX_NAME_CHARS = 32

WELCOME_TITLE = "Aquí verás las fotos de tu familia"
WELCOME_BODY = "Cuando alguien te envíe una foto, aparecerá en esta pantalla."
UNAVAILABLE_TITLE = "Esta foto no se puede mostrar"
UNAVAILABLE_BODY = "En unos segundos verás la siguiente."


@dataclass(frozen=True)
class Caption:
    sender: str | None  # "De Ana", o None si no hay nombre
    when: str  # "Hoy", "Ayer", "12 de mayo", "3 de enero de 2025"


def format_day(day: date, today: date) -> str:
    """Fecha corta y cercana. Sin "Hoy/Ayer" si la fecha es futura (reloj desajustado)."""
    delta = (today - day).days
    if delta == 0:
        return "Hoy"
    if delta == 1:
        return "Ayer"
    text = f"{day.day} de {MONTHS[day.month - 1]}"
    if day.year != today.year:
        text += f" de {day.year}"
    return text


def clean_name(name: str) -> str | None:
    """Nombre de remitente apto para pantalla: sin caracteres de control y acortado."""
    printable = "".join(c for c in name if unicodedata.category(c)[0] != "C")
    text = " ".join(printable.split())
    if not text:
        return None
    if len(text) > MAX_NAME_CHARS:
        text = text[: MAX_NAME_CHARS - 1].rstrip() + "…"
    return text


def caption_for(photo: Photo, now: datetime) -> Caption:
    """``now`` debe llevar la zona horaria local en la que se muestra la fecha."""
    local = photo.received_at.astimezone(now.tzinfo)
    name = clean_name(photo.sender_name)
    return Caption(
        sender=f"De {name}" if name else None,
        when=format_day(local.date(), now.date()),
    )


def one_line(caption: Caption) -> str:
    return caption.when if caption.sender is None else f"{caption.sender} · {caption.when}"
