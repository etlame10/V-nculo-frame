from datetime import UTC, datetime, timedelta

import pytest

from vinculo_frame.storage import Photo

BASE = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def make_photo():
    """``make_photo(id, days=...)``: foto de prueba recibida ``days`` días después de BASE."""

    def make(photo_id: int, days: float = 0, sender: str = "Ana", file_name: str | None = None):
        return Photo(
            id=photo_id,
            sha256=f"{photo_id:064x}",
            file_name=file_name or f"{photo_id:064x}.jpg",
            mime="image/jpeg",
            sender_id=f"s{photo_id}",
            sender_name=sender,
            received_at=BASE + timedelta(days=days),
            liked_at=None,
        )

    return make
