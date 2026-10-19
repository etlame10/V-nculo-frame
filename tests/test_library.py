import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from vinculo_frame.library import (
    DiskUsage,
    PhotoLibrary,
    RetentionPolicy,
    StorageFullError,
)
from vinculo_frame.media import PhotoRejected
from vinculo_frame.storage import OUTBOX_PHOTO_DELETED, LocalStore, StorageError

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
GB = 1024**3


def jpeg(tag: str, size: int = 1000) -> bytes:
    """Bytes con firma JPEG, distintos para cada ``tag`` y de tamaño exacto."""
    head = b"\xff\xd8\xff\xe0" + tag.encode()
    return head + b"\x00" * (size - len(head))


class Env:
    def __init__(self, tmp_path, limit=10_000, keep_days=30, free=10 * GB):
        self.photos_dir = tmp_path / "data" / "photos"
        self.store = LocalStore(tmp_path / "data" / "db.sqlite3")
        self.free = free
        self.policy = RetentionPolicy(limit, timedelta(days=keep_days), min_free_bytes=0)
        self.library = PhotoLibrary(
            self.store,
            self.photos_dir,
            self.policy,
            max_photo_bytes=5000,
            clock=lambda: NOW,
            disk_usage=self.disk_usage,
        )

    def disk_usage(self, _path):
        # Como un disco real: lo que ocupan las fotos deja de estar libre.
        used = (
            sum(p.stat().st_size for p in self.photos_dir.glob("*"))
            if self.photos_dir.exists()
            else 0
        )
        return DiskUsage(100 * GB, used, self.free - used)

    def add(self, tag, days_ago=0, size=1000, **kw):
        return self.library.add(
            jpeg(tag, size),
            sender_id=kw.get("sender_id", "s1"),
            sender_name=kw.get("sender_name", "Ana"),
            received_at=NOW - timedelta(days=days_ago),
        )

    def path(self, photo):
        return self.photos_dir / photo.file_name

    def files(self):
        return sorted(p.name for p in self.photos_dir.iterdir()) if self.photos_dir.exists() else []


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    e.store.close()


# --- Altas ------------------------------------------------------------------


def test_add_saves_file_and_row(env):
    photo = env.add("a")
    assert env.path(photo).read_bytes() == jpeg("a")
    assert env.store.list_photos() == [photo]
    assert not photo.is_synced


def test_duplicate_returns_existing_without_new_file(env):
    first = env.add("a")
    again = env.add("a", sender_name="Luis")
    assert again == first
    assert env.files() == [first.file_name]


def test_duplicate_with_lost_file_restores_the_file(env):
    photo = env.add("a")
    env.path(photo).unlink()
    assert env.add("a") == photo
    assert env.path(photo).exists()


def test_duplicate_of_evicted_photo_brings_it_back(env):
    photo = env.add("a", days_ago=100)
    env.store.mark_synced(photo.id, "r1")
    env.store.evict_photo(photo.id, lambda p: env.path(p).unlink(), NOW, NOW)
    assert env.store.list_photos() == []
    restored = env.add("a")
    assert restored.evicted_at is None and env.path(restored).exists()


def test_rejected_photo_leaves_nothing(env):
    with pytest.raises(PhotoRejected):
        env.library.add(b"<html>", sender_id="s", sender_name="X", received_at=NOW)
    assert env.files() == [] and env.store.list_photos() == []


def test_disk_error_while_writing_leaves_nothing(env, monkeypatch):
    def full_disk(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", full_disk)
    with pytest.raises(StorageError, match="No space left"):
        env.add("a")
    assert env.files() == [] and env.store.list_photos() == []


def test_database_error_after_writing_removes_the_new_file(env, monkeypatch):
    def broken(**kwargs):
        raise StorageError("base de datos bloqueada")

    monkeypatch.setattr(env.store, "add_photo", broken)
    with pytest.raises(StorageError, match="bloqueada"):
        env.add("a")
    assert env.files() == []


# --- Borrado ----------------------------------------------------------------


def test_delete_removes_file_and_row(env):
    keep, gone = env.add("a"), env.add("b")
    assert env.library.delete(gone.id) == gone
    assert env.files() == [keep.file_name]
    assert env.store.get_photo(gone.id) is None
    assert env.store.pending_count() == 0  # sin copia remota: nada que avisar


def test_delete_of_synced_photo_queues_remote_deletion(env):
    photo = env.add("a")
    env.store.mark_synced(photo.id, "remoto-1")
    env.library.delete(photo.id)
    (item,) = env.store.due(NOW)
    assert item.kind == OUTBOX_PHOTO_DELETED
    assert item.payload["remote_id"] == "remoto-1"


def test_delete_with_missing_file_still_removes_row(env):
    photo = env.add("a")
    env.path(photo).unlink()
    assert env.library.delete(photo.id) == photo
    assert env.store.get_photo(photo.id) is None


def test_delete_unknown_photo_returns_none(env):
    assert env.library.delete(999) is None


def test_failed_file_removal_keeps_row_and_queues_nothing(env, monkeypatch):
    photo = env.add("a")
    env.store.mark_synced(photo.id, "r1")

    def denied(self, missing_ok=False):
        raise PermissionError("solo lectura")

    monkeypatch.setattr(Path, "unlink", denied)
    with pytest.raises(PermissionError):
        env.library.delete(photo.id)
    monkeypatch.undo()
    assert env.store.get_photo(photo.id) == env.store.list_photos()[0]
    assert env.path(photo).exists()
    assert env.store.pending_count() == 0


def test_delete_refuses_unexpected_file_names(env):
    photo = env.add("a")
    env.store._conn.execute(
        "UPDATE photos SET file_name = '../../etc/passwd' WHERE id = ?", (photo.id,)
    )
    env.store._conn.commit()
    with pytest.raises(StorageError, match="inesperado"):
        env.library.delete(photo.id)
    assert env.store.get_photo(photo.id) is not None


# --- Límite y política de conservación --------------------------------------


def fill(env, specs):
    """specs: (tag, days_ago, synced, liked). Devuelve las fotos en ese orden."""
    photos = []
    for tag, days_ago, synced, liked in specs:
        photo = env.add(tag, days_ago=days_ago)
        if synced:
            env.store.mark_synced(photo.id, f"r-{tag}")
        if liked:
            env.store.mark_liked(photo.id, NOW)
        photos.append(env.store.get_photo(photo.id))
    return photos


def test_under_limit_nothing_is_evicted(env):
    fill(env, [("a", 100, True, False)])
    assert env.library.plan_eviction(1000).needed_bytes <= 0


def test_over_limit_with_only_unsynced_photos_refuses_and_deletes_nothing(tmp_path):
    env = Env(tmp_path, limit=3000)
    photos = fill(env, [(t, 100, False, False) for t in "abc"])
    with pytest.raises(StorageFullError, match="no se ha borrado nada"):
        env.add("d")
    assert env.store.list_photos() == sorted(
        photos, key=lambda p: (p.received_at, p.id), reverse=True
    )
    assert len(env.files()) == 3


def test_evicts_oldest_safe_photos_first(tmp_path):
    env = Env(tmp_path, limit=4000)
    old, older, oldest, recent = fill(
        env,
        [
            ("a", 60, True, False),
            ("b", 90, True, False),
            ("c", 120, True, False),
            ("d", 1, True, False),
        ],
    )
    new = env.add("e")
    # Se necesitaba 1 KB: solo se retira la más antigua.
    shown = {p.id for p in env.store.list_photos()}
    assert shown == {old.id, older.id, recent.id, new.id}
    evicted = env.store.get_photo(oldest.id)
    assert evicted.evicted_at == NOW and evicted.remote_id == "r-c"
    assert not env.path(oldest).exists()


@pytest.mark.parametrize(
    ("label", "spec"),
    [
        ("sin copia remota", ("a", 100, False, False)),
        ("con me gusta", ("a", 100, True, True)),
        ("reciente", ("a", 5, True, False)),
    ],
)
def test_protected_photos_are_never_evicted(tmp_path, label, spec):
    env = Env(tmp_path, limit=1000)
    (photo,) = fill(env, [spec])
    with pytest.raises(StorageFullError):
        env.add("nueva")
    assert env.path(photo).exists(), label
    assert env.store.get_photo(photo.id).evicted_at is None


def test_insufficient_plan_evicts_nothing(tmp_path):
    env = Env(tmp_path, limit=3000)
    safe, liked, unsynced = fill(
        env, [("a", 100, True, False), ("b", 100, True, True), ("c", 100, False, False)]
    )
    # Hace falta liberar 2 KB y solo hay 1 KB retirable: no se toca nada.
    with pytest.raises(StorageFullError):
        env.add("grande", size=2000)
    assert all(env.path(p).exists() for p in (safe, liked, unsynced))
    assert env.store.get_photo(safe.id).evicted_at is None


def test_low_disk_space_counts_too(tmp_path):
    env = Env(tmp_path, limit=10**9)
    env.policy = RetentionPolicy(10**9, timedelta(days=30), min_free_bytes=5000)
    env.library._policy = env.policy
    env.free = 6500  # disco libre sin fotos
    (old,) = fill(env, [("a", 100, True, False)])  # quedan 5500 libres
    env.add("b")  # quedarían 4500 < 5000 de reserva: se retira "a"
    assert env.store.get_photo(old.id).evicted_at is not None
    env.free = 1100  # "b" es reciente y no se puede retirar
    with pytest.raises(StorageFullError):
        env.add("c")


def test_evict_double_checks_safety_in_sql(env):
    photo = env.add("a", days_ago=100)
    env.store.mark_synced(photo.id, "r1")
    env.store.mark_liked(photo.id, NOW)  # entre el plan y la retirada
    removed = []
    assert env.store.evict_photo(photo.id, removed.append, NOW, NOW) is False
    assert removed == [] and env.path(photo).exists()


def test_usage_counts(env):
    a, b = fill(env, [("a", 100, True, True), ("b", 100, False, False)])
    usage = env.library.usage()
    assert usage.photo_bytes == 2000
    assert (usage.displayable, usage.evicted, usage.unsynced, usage.liked) == (2, 0, 1, 1)


def test_evicted_photos_are_hidden_from_gallery(env):
    photo = env.add("a", days_ago=100)
    env.store.mark_synced(photo.id, "r1")
    env.store.evict_photo(photo.id, lambda p: env.path(p).unlink(), NOW, NOW)
    assert env.store.list_photos() == []
    assert len(env.store.list_photos(include_evicted=True)) == 1


# --- Integridad y reparación ------------------------------------------------


def age(path, hours=2):
    old = time.time() - hours * 3600
    os.utime(path, (old, old))


def test_clean_library_is_ok(env):
    env.add("a")
    assert env.library.check(deep=True).ok


def test_check_finds_each_kind_of_problem(env):
    lost, damaged = env.add("a"), env.add("b")
    env.path(lost).unlink()
    env.path(damaged).write_bytes(jpeg("otra cosa"))
    orphan = env.photos_dir / ("f" * 64 + ".jpg")
    orphan.write_bytes(jpeg("huérfana"))
    temp = env.photos_dir / "tmpabc.part"
    temp.write_bytes(b"a medias")
    stranger = env.photos_dir / "notas.txt"
    stranger.write_text("ajeno")
    for p in (orphan, temp):
        age(p)

    report = env.library.check(deep=True)
    assert not report.ok
    assert report.missing_files == (lost,)
    assert report.orphan_files == (orphan,)
    assert report.temp_files == (temp,)
    assert report.unknown_files == (stranger,)
    assert report.corrupted == (damaged,)
    assert env.library.check(deep=False).corrupted == ()


def test_recent_orphans_are_left_alone(env):
    (env.photos_dir).mkdir(parents=True)
    (env.photos_dir / ("e" * 64 + ".jpg")).write_bytes(jpeg("x"))
    (env.photos_dir / "nuevo.part").write_bytes(b"x")
    report = env.library.check()
    assert report.orphan_files == () and report.temp_files == ()


def test_repair_is_conservative(env):
    unsynced, synced, fine = env.add("a"), env.add("b"), env.add("c")
    env.store.mark_synced(synced.id, "r-b")
    env.path(unsynced).unlink()
    env.path(synced).unlink()
    orphan = env.photos_dir / ("f" * 64 + ".jpg")
    orphan.write_bytes(jpeg("huérfana"))
    temp = env.photos_dir / "x.part"
    temp.write_bytes(b"x")
    stranger = env.photos_dir / "notas.txt"
    stranger.write_text("ajeno")
    for p in (orphan, temp):
        age(p)

    result = env.library.repair(env.library.check())
    assert (result.removed_rows, result.evicted_rows) == (1, 1)
    assert (result.quarantined_files, result.removed_temp_files) == (1, 1)
    assert env.store.get_photo(unsynced.id) is None  # perdida sin copia: se borra la fila
    assert env.store.get_photo(synced.id).evicted_at == NOW  # se podrá recuperar
    assert (env.library.quarantine_dir / orphan.name).read_bytes() == jpeg("huérfana")
    assert not temp.exists() and stranger.exists()
    assert env.path(fine).exists()
    assert env.library.check().ok


def test_repair_refuses_when_all_files_are_missing(env):
    photos = [env.add(t) for t in "abc"]
    for p in photos:
        env.path(p).unlink()
    with pytest.raises(StorageError, match="desmontado"):
        env.library.repair(env.library.check())
    assert len(env.store.list_photos()) == 3


def test_repair_refuses_when_photos_dir_is_missing(env):
    env.add("a")
    for p in env.photos_dir.iterdir():
        p.unlink()
    env.photos_dir.rmdir()
    report = env.library.check()
    assert report.photos_dir_missing
    with pytest.raises(StorageError, match="carpeta"):
        env.library.repair(report)
    assert len(env.store.list_photos()) == 1


def test_repair_refuses_on_database_errors(env):
    from vinculo_frame.library import IntegrityReport

    with pytest.raises(StorageError, match="integridad"):
        env.library.repair(IntegrityReport(database_errors=("página dañada",)))


def test_interrupted_add_cleans_its_file(env, monkeypatch):
    """Interrupción entre escribir el archivo y registrar la fila: no queda huérfano.

    Si el proceso muere sin poder limpiar, ``check`` lo detecta como huérfano
    (ver test_check_finds_each_kind_of_problem).
    """
    monkeypatch.setattr(
        env.store, "add_photo", lambda **kw: (_ for _ in ()).throw(KeyboardInterrupt)
    )
    with pytest.raises(KeyboardInterrupt):
        env.add("a")
    # add() limpia su propio archivo incluso con KeyboardInterrupt.
    assert env.files() == []
