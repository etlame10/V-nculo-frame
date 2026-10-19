import itertools
from datetime import UTC, datetime, timedelta

import pytest

from vinculo_frame.sos import SosMachine, SosState
from vinculo_frame.sos_service import (
    OUTBOX_SOS_ACK,
    OUTBOX_SOS_ALERT,
    OUTBOX_SOS_RESOLVED,
    SosService,
)
from vinculo_frame.storage import LocalStore

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeAlarm:
    def __init__(self):
        self.calls = []

    def start(self, alert_id):
        self.calls.append(("start", alert_id))

    def stop(self, alert_id):
        self.calls.append(("stop", alert_id))


@pytest.fixture
def setup(tmp_path):
    seconds = itertools.count()
    store = LocalStore(tmp_path / "db.sqlite3")
    alarm = FakeAlarm()
    service = SosService(
        SosMachine(hold_seconds=2.5, new_alert_id=lambda: "a1"),
        store,
        alarm,
        wall_clock=lambda: T0 + timedelta(seconds=next(seconds)),
    )
    yield service, store, alarm
    store.close()


def test_full_flow_without_internet_leaves_pending_notices(setup):
    service, store, alarm = setup

    service.press(0.0)
    service.tick(3.0)
    assert alarm.calls == [("start", "a1")]
    assert service.machine.state is SosState.ALERTING

    # Sin conexión: el aviso queda en la cola local.
    pending = store.due(T0 + timedelta(hours=1))
    assert [(i.kind, i.payload["alert_id"]) for i in pending] == [(OUTBOX_SOS_ALERT, "a1")]

    service.acknowledge("a1", "ana", 30.0)
    service.acknowledge("a1", "ana", 31.0)  # duplicada: sin efecto
    service.resolve("a1", "ana", 60.0)

    assert alarm.calls == [("start", "a1"), ("stop", "a1")]
    kinds = [i.kind for i in store.due(T0 + timedelta(hours=1))]
    assert kinds == [OUTBOX_SOS_ALERT, OUTBOX_SOS_ACK, OUTBOX_SOS_RESOLVED]

    record = store.get_sos("a1")
    assert [m for m, _ in record.acks] == ["ana"]
    assert record.resolved_by == "ana"


def test_short_press_has_no_side_effects(setup):
    service, store, alarm = setup
    service.press(0.0)
    service.release(1.0)
    assert alarm.calls == []
    assert store.pending_count() == 0
