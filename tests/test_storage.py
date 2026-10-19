from datetime import UTC, datetime, timedelta

import pytest

from vinculo_frame.storage import SCHEMA_VERSION, LocalStore, StorageError, backoff

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    with LocalStore(tmp_path / "data" / "test.sqlite3") as s:
        yield s


def add(store, sha="a" * 64, at=T0, sender="ana"):
    return store.add_photo(
        sha256=sha,
        file_name=f"{sha}.jpg",
        mime="image/jpeg",
        sender_id=sender,
        sender_name=sender.title(),
        received_at=at,
    )


def test_add_photo_is_idempotent_by_content(store):
    first = add(store)
    again = add(store, sender="luis")
    assert again == first
    assert len(store.list_photos()) == 1


def test_list_photos_newest_first(store):
    add(store, "a" * 64, T0)
    add(store, "b" * 64, T0 + timedelta(hours=1))
    assert [p.sha256[0] for p in store.list_photos()] == ["b", "a"]


def test_mark_liked_only_once(store):
    photo = add(store)
    assert store.mark_liked(photo.id, T0) is True
    assert store.mark_liked(photo.id, T0 + timedelta(minutes=1)) is False
    assert store.list_photos()[0].liked_at == T0


def test_mark_liked_unknown_photo(store):
    with pytest.raises(StorageError):
        store.mark_liked(999, T0)


def test_naive_datetimes_are_rejected(store):
    with pytest.raises(StorageError):
        store.enqueue("x", {}, datetime(2026, 1, 1))


def test_outbox_due_and_sent(store):
    item_id = store.enqueue("sos_alert", {"alert_id": "a1", "texto": "¡ayuda!"}, T0)
    due = store.due(T0)
    assert [i.id for i in due] == [item_id]
    assert due[0].payload == {"alert_id": "a1", "texto": "¡ayuda!"}
    store.mark_sent(item_id, T0)
    assert store.due(T0 + timedelta(days=1)) == []
    assert store.pending_count() == 0


def test_outbox_failure_schedules_retry_with_backoff(store):
    item_id = store.enqueue("sos_alert", {}, T0)
    next_at = store.mark_failed(item_id, "sin conexión", T0)
    assert next_at == T0 + timedelta(seconds=5)
    assert store.due(T0 + timedelta(seconds=4)) == []
    assert [i.attempts for i in store.due(next_at)] == [1]
    next_at = store.mark_failed(item_id, "sin conexión", next_at)
    assert store.due(next_at - timedelta(seconds=1)) == []
    assert store.pending_count() == 1


def test_outbox_due_preserves_order_and_limit(store):
    ids = [store.enqueue("k", {"n": n}, T0) for n in range(5)]
    assert [i.id for i in store.due(T0, limit=3)] == ids[:3]


def test_mark_failed_on_sent_item_is_an_error(store):
    item_id = store.enqueue("k", {}, T0)
    store.mark_sent(item_id, T0)
    with pytest.raises(StorageError):
        store.mark_failed(item_id, "x", T0)


def test_backoff_is_exponential_and_capped():
    assert [backoff(n).total_seconds() for n in (1, 2, 3, 4)] == [5, 10, 20, 40]
    assert backoff(30).total_seconds() == 300


def test_sos_record_lifecycle(store):
    store.record_sos_triggered("a1", T0)
    store.record_sos_ack("a1", "ana", T0 + timedelta(seconds=30))
    store.record_sos_ack("a1", "ana", T0 + timedelta(seconds=40))  # repetida
    store.record_sos_resolved("a1", "ana", T0 + timedelta(minutes=5))
    record = store.get_sos("a1")
    assert record.acks == (("ana", T0 + timedelta(seconds=30)),)
    assert record.resolved_by == "ana"
    assert record.resolved_at == T0 + timedelta(minutes=5)


def test_sos_ack_for_unknown_alert(store):
    with pytest.raises(StorageError):
        store.record_sos_ack("nada", "ana", T0)


def test_sos_resolve_unknown_alert(store):
    with pytest.raises(StorageError):
        store.record_sos_resolved("nada", "ana", T0)


def test_data_survives_reopen(tmp_path):
    path = tmp_path / "db.sqlite3"
    with LocalStore(path) as s:
        s.enqueue("sos_alert", {"alert_id": "a1"}, T0)
    with LocalStore(path) as s:
        assert s.pending_count() == 1


def test_newer_schema_is_rejected(tmp_path):
    path = tmp_path / "db.sqlite3"
    with LocalStore(path) as s:
        s._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(StorageError):
        LocalStore(path)
