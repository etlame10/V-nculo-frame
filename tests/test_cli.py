import pytest

from vinculo_frame.__main__ import main


def test_check_creates_local_storage_and_hides_secrets(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VINCULO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:supersecreto")
    assert main(["check"]) == 0
    out = capsys.readouterr().out
    assert "Telegram:        configurado" in out
    assert "supersecreto" not in out
    assert (tmp_path / "data" / "vinculo.sqlite3").exists()
    assert (tmp_path / "data" / "photos").is_dir()


def test_check_reports_invalid_config(monkeypatch, capsys):
    monkeypatch.setenv("VINCULO_SOS_HOLD_SECONDS", "99")
    assert main(["check"]) == 2
    assert "VINCULO_SOS_HOLD_SECONDS" in capsys.readouterr().err


def _jpeg(tag):
    return b"\xff\xd8\xff\xe0" + tag.encode() + b"\x00" * 100


def _seed(tmp_path, monkeypatch, tags=("a", "b")):
    from datetime import UTC, datetime

    from vinculo_frame.config import load_settings
    from vinculo_frame.library import PhotoLibrary
    from vinculo_frame.storage import LocalStore

    monkeypatch.setenv("VINCULO_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    with LocalStore(settings.database_path) as store:
        library = PhotoLibrary.from_settings(store, settings)
        return settings, [
            library.add(_jpeg(t), sender_id="s", sender_name="Ana", received_at=datetime.now(UTC))
            for t in tags
        ]


def test_storage_report_ok(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, monkeypatch)
    assert main(["storage", "--deep"]) == 0
    out = capsys.readouterr().out
    assert "v2" in out and "Integridad: correcta" in out and "Fotos en pantalla: 2" in out


def test_storage_reports_and_repairs_problems(tmp_path, monkeypatch, capsys):
    settings, (lost, _) = _seed(tmp_path, monkeypatch)
    (settings.photos_dir / lost.file_name).unlink()
    assert main(["storage"]) == 3
    assert "Fotos sin archivo: 1" in capsys.readouterr().out
    assert main(["storage", "--repair"]) == 0
    assert "1 filas sin archivo borradas" in capsys.readouterr().out
    assert main(["storage"]) == 0


def test_backup_command(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, monkeypatch)
    out = tmp_path / "copia.sqlite3"
    assert main(["backup", "--out", str(out)]) == 0
    assert out.exists()


def test_delete_photo_requires_confirmation(tmp_path, monkeypatch, capsys):
    settings, (photo, _) = _seed(tmp_path, monkeypatch)
    assert main(["delete-photo", "--id", str(photo.id)]) == 2
    assert (settings.photos_dir / photo.file_name).exists()
    assert main(["delete-photo", "--id", str(photo.id), "--yes"]) == 0
    assert not (settings.photos_dir / photo.file_name).exists()
    assert main(["delete-photo", "--id", str(photo.id), "--yes"]) == 1


@pytest.mark.parametrize("count", ["0", "9", "seis"])
def test_demo_photos_rejects_bad_count_without_traceback(count, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["demo-photos", "--count", count])
    assert exc.value.code == 2
    assert "--count" in capsys.readouterr().err


def test_commands_report_a_damaged_database(tmp_path, monkeypatch, capsys):
    data = tmp_path / "data"
    data.mkdir()
    (data / "vinculo.sqlite3").write_bytes(b"no es sqlite" * 100)
    monkeypatch.setenv("VINCULO_DATA_DIR", str(data))
    assert main(["storage"]) == 1
    assert main(["backup", "--out", str(tmp_path / "c.sqlite3")]) == 1
    assert main(["delete-photo", "--id", "1", "--yes"]) == 1
    assert capsys.readouterr().err.count("dañada") == 3
    assert (data / "vinculo.sqlite3").read_bytes() == b"no es sqlite" * 100


def test_storage_repair_refuses_possible_unmount(tmp_path, monkeypatch, capsys):
    settings, photos = _seed(tmp_path, monkeypatch)
    for photo in photos:
        (settings.photos_dir / photo.file_name).unlink()
    assert main(["storage", "--repair"]) == 1
    assert "desmontado" in capsys.readouterr().err
    assert main(["storage"]) == 3  # nada se ha borrado: siguen faltando


def test_backup_to_unwritable_place_fails_cleanly(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, monkeypatch)
    blocker = tmp_path / "un-archivo"
    blocker.write_text("x")
    assert main(["backup", "--out", str(blocker / "copia.sqlite3")]) == 1
    assert "No se ha podido hacer la copia" in capsys.readouterr().err
