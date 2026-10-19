import sqlite3
from datetime import UTC, datetime

import pytest

from vinculo_frame import storage
from vinculo_frame.storage import SCHEMA_VERSION, LocalStore, MigrationError, StorageError

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def make_v1_database(path):
    """Base de datos como la creaba la fase 1: mismas sentencias y user_version = 1."""
    conn = sqlite3.connect(path)
    for statement in storage._MIGRATIONS[0]:
        conn.execute(statement)
    conn.execute("PRAGMA user_version = 1")
    conn.execute(
        "INSERT INTO photos (sha256, file_name, mime, sender_id, sender_name, received_at,"
        " liked_at) VALUES (?, ?, 'image/jpeg', 's1', 'Ana', ?, ?)",
        ("a" * 64, "a" * 64 + ".jpg", T0.isoformat(), T0.isoformat()),
    )
    conn.execute(
        "INSERT INTO outbox (kind, payload, created_at, next_attempt_at)"
        " VALUES ('sos_alert', '{}', ?, ?)",
        (T0.isoformat(), T0.isoformat()),
    )
    conn.execute(
        "INSERT INTO sos_alerts (alert_id, triggered_at) VALUES ('a1', ?)", (T0.isoformat(),)
    )
    conn.commit()
    conn.close()


def columns(path, table="photos"):
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_fresh_database_is_created_at_latest_version(tmp_path):
    with LocalStore(tmp_path / "db.sqlite3") as store:
        assert store.schema_version == SCHEMA_VERSION == 2
    assert {"remote_id", "evicted_at"} <= columns(tmp_path / "db.sqlite3")
    # Una base de datos nueva no necesita copia previa.
    assert not list(tmp_path.glob("*.bak"))


def test_v1_to_v2_keeps_all_data_and_makes_backup(tmp_path):
    path = tmp_path / "db.sqlite3"
    make_v1_database(path)
    with LocalStore(path) as store:
        assert store.schema_version == 2
        (photo,) = store.list_photos()
        assert photo.sender_name == "Ana" and photo.liked_at == T0
        assert photo.remote_id is None and photo.evicted_at is None
        assert not photo.is_synced
        assert store.pending_count() == 1
        assert store.get_sos("a1") is not None
        assert store.quick_check() == []

    backup = tmp_path / "db.sqlite3.v1.bak"
    assert backup.exists()
    conn = sqlite3.connect(backup)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0] == 1
    conn.close()


def test_reopening_does_not_migrate_or_back_up_again(tmp_path):
    path = tmp_path / "db.sqlite3"
    make_v1_database(path)
    LocalStore(path).close()
    (tmp_path / "db.sqlite3.v1.bak").unlink()
    LocalStore(path).close()
    assert not list(tmp_path.glob("*.bak"))


def test_failed_migration_rolls_back_completely(tmp_path, monkeypatch):
    path = tmp_path / "db.sqlite3"
    with LocalStore(path) as store:
        store.enqueue("k", {"n": 1}, T0)

    # v2 → v3 ficticia: la primera sentencia funciona, la segunda falla.
    broken = (*storage._MIGRATIONS, ("ALTER TABLE photos ADD COLUMN extra TEXT", "NO ES SQL"))
    monkeypatch.setattr(storage, "_MIGRATIONS", broken)
    with pytest.raises(MigrationError, match="sigue en v2"):
        LocalStore(path)

    assert "extra" not in columns(path)  # la parte que sí funcionó también se deshizo
    monkeypatch.undo()
    with LocalStore(path) as store:
        assert store.schema_version == 2
        assert store.pending_count() == 1
    assert (tmp_path / "db.sqlite3.v2.bak").exists()


def test_failed_v1_migration_leaves_v1_usable(tmp_path, monkeypatch):
    path = tmp_path / "db.sqlite3"
    make_v1_database(path)
    broken = (storage._MIGRATIONS[0], ("ALTER TABLE photos ADD COLUMN remote_id TEXT", "NO"))
    monkeypatch.setattr(storage, "_MIGRATIONS", broken)
    with pytest.raises(MigrationError):
        LocalStore(path)
    assert "remote_id" not in columns(path)
    monkeypatch.undo()
    with LocalStore(path) as store:  # el siguiente arranque migra con éxito
        assert store.schema_version == 2
        assert len(store.list_photos()) == 1


def test_corrupted_database_is_reported_and_left_untouched(tmp_path):
    path = tmp_path / "db.sqlite3"
    garbage = b"esto no es una base de datos SQLite" * 100
    path.write_bytes(garbage)
    with pytest.raises(StorageError, match="dañada"):
        LocalStore(path)
    assert path.read_bytes() == garbage


def test_newer_schema_is_rejected_without_changes(tmp_path):
    path = tmp_path / "db.sqlite3"
    LocalStore(path).close()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    with pytest.raises(StorageError, match="más nueva"):
        LocalStore(path)
    assert not list(tmp_path.glob("*.bak"))


def test_backup_is_a_consistent_copy(tmp_path):
    with LocalStore(tmp_path / "db.sqlite3") as store:
        store.enqueue("k", {}, T0)
        store.backup(tmp_path / "copias" / "copia.sqlite3")
    with LocalStore(tmp_path / "copias" / "copia.sqlite3") as copy:
        assert copy.pending_count() == 1
    assert not list((tmp_path / "copias").glob("*.tmp"))
