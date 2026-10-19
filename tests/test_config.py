from pathlib import Path

import pytest

from vinculo_frame.config import ConfigError, load_settings


def test_defaults_work_without_any_cloud_credentials():
    s = load_settings({})
    assert s.data_dir == Path("./data")
    assert s.sos_hold_seconds == 2.5
    assert s.database_path == Path("./data/vinculo.sqlite3")
    assert not s.telegram_enabled
    assert not s.supabase_enabled


def test_reads_values():
    s = load_settings(
        {
            "VINCULO_DATA_DIR": "/srv/vinculo",
            "VINCULO_SLIDE_SECONDS": "20",
            "VINCULO_SOS_HOLD_SECONDS": "3",
            "VINCULO_MAX_PHOTO_MB": "5",
            "VINCULO_LOG_LEVEL": "debug",
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_ANON_KEY": "publica",
            "SUPABASE_DEVICE_EMAIL": "marco@example.invalid",
            "SUPABASE_DEVICE_PASSWORD": "secreto",
        }
    )
    assert s.photos_dir == Path("/srv/vinculo/photos")
    assert s.slide_seconds == 20
    assert s.sos_hold_seconds == 3
    assert s.max_photo_bytes == 5 * 1024 * 1024
    assert s.log_level == "DEBUG"
    assert s.telegram_enabled and s.supabase_enabled


def test_blank_values_count_as_missing():
    s = load_settings({"TELEGRAM_BOT_TOKEN": "  ", "VINCULO_SOS_HOLD_SECONDS": ""})
    assert not s.telegram_enabled
    assert s.sos_hold_seconds == 2.5


def test_secrets_are_not_in_repr():
    s = load_settings(
        {"TELEGRAM_BOT_TOKEN": "123:supersecreto", "SUPABASE_DEVICE_PASSWORD": "clave-privada"}
    )
    assert "supersecreto" not in repr(s)
    assert "clave-privada" not in repr(s)


@pytest.mark.parametrize(
    "env",
    [
        {"VINCULO_SOS_HOLD_SECONDS": "abc"},
        {"VINCULO_SOS_HOLD_SECONDS": "0.2"},
        {"VINCULO_SLIDE_SECONDS": "1"},
        {"VINCULO_MAX_PHOTO_MB": "500"},
        {"VINCULO_LOG_LEVEL": "VERBOSE"},
        {"SUPABASE_URL": "http://inseguro.example.com"},
    ],
)
def test_invalid_values(env):
    with pytest.raises(ConfigError):
        load_settings(env)


def test_supabase_needs_all_device_credentials():
    s = load_settings({"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_ANON_KEY": "k"})
    assert not s.supabase_enabled
