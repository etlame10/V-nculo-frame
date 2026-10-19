from vinculo_frame.gallery.playlist import Playlist


def ids(playlist, n, now=0.0):
    return [playlist.next(now).id for _ in range(n)]


def test_empty_playlist_returns_none():
    playlist = Playlist()
    playlist.update([])
    assert playlist.next(0.0) is None
    assert len(playlist) == 0


def test_rotation_newest_first_and_wraps(make_photo):
    playlist = Playlist()
    # Desordenadas a propósito: el orden lo decide la fecha, no la entrada.
    playlist.update([make_photo(1, days=1), make_photo(3, days=3), make_photo(2, days=2)])
    assert ids(playlist, 7) == [3, 2, 1, 3, 2, 1, 3]


def test_same_date_is_ordered_by_id(make_photo):
    playlist = Playlist()
    playlist.update([make_photo(1), make_photo(2)])
    assert ids(playlist, 3) == [2, 1, 2]


def test_single_photo_repeats(make_photo):
    playlist = Playlist()
    playlist.update([make_photo(1)])
    assert ids(playlist, 3) == [1, 1, 1]


def test_initial_load_does_not_count_as_new(make_photo):
    playlist = Playlist()
    assert playlist.update([make_photo(1), make_photo(2, days=1)]) == 0


def test_new_photo_is_shown_next_then_rotation_continues(make_photo):
    playlist = Playlist()
    old = [make_photo(1, days=1), make_photo(2, days=2), make_photo(3, days=3)]
    playlist.update(old)
    assert ids(playlist, 2) == [3, 2]
    assert playlist.update([*old, make_photo(9, days=9)]) == 1
    assert ids(playlist, 3) == [9, 3, 2]


def test_several_new_photos_newest_first(make_photo):
    playlist = Playlist()
    playlist.update([make_photo(1)])
    playlist.next(0.0)
    playlist.update([make_photo(1), make_photo(5, days=5), make_photo(6, days=6)])
    assert ids(playlist, 2) == [6, 5]


def test_deleted_current_photo_continues_with_next_older(make_photo):
    playlist = Playlist()
    a, b, c = make_photo(1, days=1), make_photo(2, days=2), make_photo(3, days=3)
    playlist.update([a, b, c])
    assert ids(playlist, 2) == [3, 2]
    playlist.update([a, c])  # se borra la foto actual
    assert ids(playlist, 2) == [1, 3]


def test_deleted_pending_photo_is_not_shown(make_photo):
    playlist = Playlist()
    playlist.update([make_photo(1)])
    playlist.update([make_photo(1), make_photo(2, days=2)])
    playlist.update([make_photo(1)])
    assert ids(playlist, 2) == [1, 1]


def test_failed_photo_is_skipped_until_retry(make_photo):
    playlist = Playlist(retry_after=60)
    playlist.update([make_photo(1, days=1), make_photo(2, days=2), make_photo(3, days=3)])
    assert playlist.next(0.0).id == 3
    playlist.mark_failed(2, now=0.0)
    assert [playlist.next(t).id for t in (1.0, 2.0, 3.0)] == [1, 3, 1]
    assert [playlist.next(t).id for t in (61.0, 62.0)] == [3, 2]


def test_when_all_photos_fail_they_are_still_tried(make_photo):
    playlist = Playlist(retry_after=60)
    playlist.update([make_photo(1, days=1), make_photo(2, days=2)])
    playlist.mark_failed(1, 0.0)
    playlist.mark_failed(2, 0.0)
    assert ids(playlist, 3, now=1.0) == [2, 1, 2]


def test_failed_pending_photo_waits_for_rotation(make_photo):
    playlist = Playlist(retry_after=60)
    playlist.update([make_photo(1)])
    playlist.next(0.0)
    playlist.update([make_photo(1), make_photo(2, days=2)])
    playlist.mark_failed(2, 0.0)
    assert playlist.next(1.0).id == 1
