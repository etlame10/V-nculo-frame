import pytest

from vinculo_frame.gallery.controller import (
    UNAVAILABLE_SECONDS,
    GalleryController,
    PhotoSlide,
    UnavailableSlide,
    WelcomeSlide,
)


class FakeStore:
    def __init__(self, photos=()):
        self.photos = list(photos)
        self.fail = False
        self.calls = 0

    def list_photos(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("database is locked")
        return list(self.photos)


class FakeLoader:
    def __init__(self, broken=()):
        self.broken = set(broken)
        self.loaded = []

    def __call__(self, photo):
        self.loaded.append(photo.id)
        if photo.id in self.broken:
            raise OSError("archivo truncado")
        return f"imagen-{photo.id}"


def make(store, loader=None, slide=10.0, refresh=30.0):
    return GalleryController(store.list_photos, loader or FakeLoader(), slide, refresh)


def test_empty_gallery_shows_welcome_once():
    controller = make(FakeStore())
    assert controller.tick(0.0) == WelcomeSlide()
    assert controller.tick(1.0) is None
    assert controller.tick(10.0) is None  # sigue la bienvenida, sin redibujar


def test_photo_slides_rotate_after_interval(make_photo):
    store = FakeStore([make_photo(1, days=1), make_photo(2, days=2)])
    controller = make(store)
    first = controller.tick(0.0)
    assert isinstance(first, PhotoSlide) and first.photo.id == 2
    assert first.image == "imagen-2"
    assert controller.tick(9.9) is None
    assert controller.tick(10.0).photo.id == 1
    assert controller.tick(20.0).photo.id == 2


def test_first_photo_replaces_welcome_at_next_refresh(make_photo):
    store = FakeStore()
    controller = make(store, refresh=30.0)
    assert controller.tick(0.0) == WelcomeSlide()
    store.photos = [make_photo(1)]
    assert controller.tick(29.0) is None
    assert controller.tick(30.0).photo.id == 1


def test_new_photo_is_shown_immediately_on_refresh(make_photo):
    store = FakeStore([make_photo(1), make_photo(2, days=1)])
    controller = make(store, slide=60.0, refresh=5.0)
    controller.tick(0.0)
    store.photos.append(make_photo(3, days=3))
    assert controller.tick(5.0).photo.id == 3


def test_single_photo_is_not_reloaded(make_photo):
    loader = FakeLoader()
    controller = make(FakeStore([make_photo(1)]), loader)
    controller.tick(0.0)
    assert controller.tick(10.0) is None
    assert controller.tick(20.0) is None
    assert loader.loaded == [1]


def test_read_error_shows_message_and_continues(make_photo):
    store = FakeStore([make_photo(1, days=1), make_photo(2, days=2)])
    controller = make(store, FakeLoader(broken={2}), slide=15.0)
    slide = controller.tick(0.0)
    assert slide == UnavailableSlide(make_photo(2, days=2))
    # El aviso dura menos que una foto normal.
    assert controller.tick(UNAVAILABLE_SECONDS - 0.1) is None
    assert controller.tick(UNAVAILABLE_SECONDS).photo.id == 1
    # La foto rota se salta en la siguiente vuelta.
    assert controller.tick(UNAVAILABLE_SECONDS + 15.0) is None


def test_all_photos_broken_keeps_showing_messages(make_photo):
    controller = make(FakeStore([make_photo(1)]), FakeLoader(broken={1}))
    assert isinstance(controller.tick(0.0), UnavailableSlide)
    assert controller.tick(100.0) is None  # mismo aviso, sin bloquear
    assert isinstance(controller.current, UnavailableSlide)


def test_storage_error_keeps_previous_photos(make_photo):
    store = FakeStore([make_photo(1), make_photo(2, days=1)])
    controller = make(store, refresh=5.0)
    controller.tick(0.0)
    store.fail = True
    assert controller.tick(10.0).photo.id == 1
    assert store.calls == 2


def test_storage_error_on_first_load_shows_welcome():
    store = FakeStore()
    store.fail = True
    controller = make(store)
    assert controller.tick(0.0) == WelcomeSlide()


def test_skip_advances_immediately(make_photo):
    controller = make(FakeStore([make_photo(1), make_photo(2, days=1)]))
    controller.tick(0.0)
    assert controller.skip(1.0).photo.id == 1
    assert controller.tick(10.0) is None  # el intervalo cuenta desde el salto
    assert controller.tick(11.0).photo.id == 2


@pytest.mark.parametrize(("slide", "refresh"), [(0, 30), (10, 0), (-1, 30)])
def test_invalid_intervals(slide, refresh):
    with pytest.raises(ValueError):
        GalleryController(list, lambda p: p, slide, refresh)
