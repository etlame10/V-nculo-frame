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
