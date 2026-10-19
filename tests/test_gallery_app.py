import os
from datetime import UTC, datetime

import pytest

pytest.importorskip("PIL")

from vinculo_frame.__main__ import main  # noqa: E402
from vinculo_frame.config import load_settings  # noqa: E402
from vinculo_frame.gallery.app import render_previews  # noqa: E402
from vinculo_frame.gallery.demo import create_demo_photos  # noqa: E402
from vinculo_frame.storage import LocalStore  # noqa: E402

NOW = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path):
    return load_settings({"VINCULO_DATA_DIR": str(tmp_path / "data")})


def test_demo_photos_use_existing_storage(settings):
    with LocalStore(settings.database_path) as store:
        photos = create_demo_photos(store, settings.photos_dir, NOW, count=3, with_broken=True)
        assert len(store.list_photos()) == 4
    assert all(p.sender_id.startswith("demo-") for p in photos)
    assert sorted(f.name for f in settings.photos_dir.iterdir()) == sorted(
        p.file_name for p in photos
    )


def test_demo_photos_are_idempotent(settings):
    with LocalStore(settings.database_path) as store:
        create_demo_photos(store, settings.photos_dir, NOW, count=2)
        create_demo_photos(store, settings.photos_dir, NOW, count=2)
        assert len(store.list_photos()) == 2


def test_demo_count_validated(settings):
    with LocalStore(settings.database_path) as store, pytest.raises(ValueError):
        create_demo_photos(store, settings.photos_dir, NOW, count=0)


def test_previews_cover_welcome_photos_and_broken(settings, tmp_path):
    empty = render_previews(settings, tmp_path / "empty", (640, 360), 1, NOW)
    assert len(empty) == 1 and empty[0].exists()

    with LocalStore(settings.database_path) as store:
        create_demo_photos(store, settings.photos_dir, NOW, count=2, with_broken=True)
    paths = render_previews(settings, tmp_path / "out", (360, 640), 4, NOW)
    assert [p.name for p in paths] == [f"diapositiva-0{i}.png" for i in range(1, 5)]


def test_cli_demo_and_preview(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VINCULO_DATA_DIR", str(tmp_path / "data"))
    assert main(["demo-photos", "--count", "2"]) == 0
    assert (
        main(["preview", "--out", str(tmp_path / "p"), "--size", "320x240", "--slides", "2"]) == 0
    )
    assert len(list((tmp_path / "p").glob("*.png"))) == 2
    assert "2 fotos ficticias" in capsys.readouterr().out


def test_cli_rejects_bad_size(capsys):
    with pytest.raises(SystemExit):
        main(["preview", "--size", "grande"])
    assert "ANCHOxALTO" in capsys.readouterr().err


def test_cli_gallery_headless(tmp_path, monkeypatch):
    pytest.importorskip("pygame")
    monkeypatch.setenv("SDL_VIDEODRIVER", os.environ.get("SDL_VIDEODRIVER", "dummy"))
    monkeypatch.setenv("VINCULO_DATA_DIR", str(tmp_path / "data"))
    assert main(["demo-photos", "--count", "1"]) == 0
    shot = tmp_path / "shot.png"
    args = ["gallery", "--windowed", "--size", "320x240", "--max-seconds", "0.3"]
    assert main([*args, "--screenshot", str(shot)]) == 0
    assert shot.exists()
