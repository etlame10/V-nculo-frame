from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from vinculo_frame.gallery.captions import Caption, caption_for, clean_name, format_day, one_line
from vinculo_frame.gallery.layout import contain, cover, metrics, parse_size

TODAY = date(2026, 10, 19)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 19), "Hoy"),
        (date(2026, 10, 18), "Ayer"),
        (date(2026, 5, 3), "3 de mayo"),
        (date(2025, 12, 31), "31 de diciembre de 2025"),
        (date(2026, 10, 25), "25 de octubre"),  # reloj desajustado: sin "Hoy"
    ],
)
def test_format_day(day, expected):
    assert format_day(day, TODAY) == expected


def test_caption_uses_local_timezone(make_photo):
    madrid_summer = timezone(timedelta(hours=2))
    photo = replace(make_photo(1), received_at=datetime(2026, 10, 18, 23, 30, tzinfo=UTC))
    now = datetime(2026, 10, 19, 9, 0, tzinfo=madrid_summer)
    assert caption_for(photo, now) == Caption("De Ana", "Hoy")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Ana   María ", "Ana María"),
        ("Luis\n\x07", "Luis"),
        ("", None),
        ("\u200b", None),  # espacio de ancho cero
        ("A" * 40, "A" * 31 + "…"),
    ],
)
def test_clean_name(raw, expected):
    assert clean_name(raw) == expected


def test_caption_without_sender(make_photo):
    now = datetime(2026, 5, 1, 13, 0, tzinfo=UTC)
    caption = caption_for(make_photo(1, sender=" "), now)
    assert caption == Caption(None, "Hoy")
    assert one_line(caption) == "Hoy"
    assert one_line(Caption("De Ana", "Ayer")) == "De Ana · Ayer"


def test_contain_and_cover():
    assert contain((4000, 3000), (1920, 1080)) == (1440, 1080)
    assert contain((3000, 4000), (1080, 1920)) == (1080, 1440)
    assert cover((4000, 3000), (1920, 1080)) == (1920, 1440)


@pytest.mark.parametrize("size", [(1920, 1080), (1080, 1920), (800, 480), (480, 800)])
def test_metrics_scale_with_short_side_and_fit(size):
    m = metrics(size)
    assert m.title_px > m.body_px >= 22
    assert m.band_height <= size[1] // 2
    assert metrics(size[::-1]) == m  # misma letra en horizontal y vertical


def test_parse_size():
    assert parse_size("1920x1080") == (1920, 1080)
    for bad in ("1920", "ax1", "50x50", "0x100"):
        with pytest.raises(ValueError):
            parse_size(bad)
