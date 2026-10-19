import itertools

import pytest

from vinculo_frame.sos import (
    AnnounceAcknowledged,
    RecordResolved,
    SendSosAlert,
    SosError,
    SosMachine,
    SosState,
    StartLocalAlarm,
    StopLocalAlarm,
    UnknownAlertError,
)


@pytest.fixture
def machine() -> SosMachine:
    ids = (f"alert-{n}" for n in itertools.count(1))
    return SosMachine(hold_seconds=2.5, new_alert_id=lambda: next(ids))


def trigger(m: SosMachine, start: float = 0.0) -> str:
    m.press(start)
    m.tick(start + 3.0)
    assert m.alert_id is not None
    return m.alert_id


def test_starts_idle(machine):
    assert machine.state is SosState.IDLE
    assert machine.alert_id is None


def test_short_press_does_nothing(machine):
    assert machine.press(0.0) == []
    assert machine.state is SosState.HOLDING
    assert machine.tick(1.0) == []
    assert machine.release(1.2) == []
    assert machine.state is SosState.IDLE


def test_long_press_triggers_alert_on_tick(machine):
    machine.press(10.0)
    assert machine.tick(12.4) == []
    effects = machine.tick(12.5)
    assert effects == [StartLocalAlarm("alert-1"), SendSosAlert("alert-1", 12.5)]
    assert machine.state is SosState.ALERTING
    assert machine.alert_id == "alert-1"


def test_long_press_triggers_on_release_if_no_tick_arrived(machine):
    machine.press(0.0)
    effects = machine.release(4.0)
    assert effects == [StartLocalAlarm("alert-1"), SendSosAlert("alert-1", 4.0)]
    assert machine.state is SosState.ALERTING


def test_release_after_trigger_keeps_alert(machine):
    trigger(machine)
    assert machine.release(5.0) == []
    assert machine.state is SosState.ALERTING


def test_repeated_press_while_holding_does_not_restart_timer(machine):
    machine.press(0.0)
    machine.press(2.0)  # rebote del botón
    assert machine.tick(2.5) != []


def test_presses_during_active_alert_do_not_create_new_alerts(machine):
    trigger(machine)
    for t in (5.0, 15.0, 25.0):
        assert machine.press(t) == []
        assert machine.tick(t + 5) == []
        assert machine.release(t + 6) == []
    assert machine.alert_id == "alert-1"


def test_repeated_ticks_trigger_only_once(machine):
    machine.press(0.0)
    assert len(machine.tick(3.0)) == 2
    assert machine.tick(4.0) == []
    assert machine.tick(5.0) == []


def test_release_or_tick_while_idle_is_ignored(machine):
    assert machine.release(1.0) == []
    assert machine.tick(2.0) == []
    assert machine.state is SosState.IDLE


def test_acknowledge_moves_to_acknowledged_once_per_member(machine):
    alert = trigger(machine)
    assert machine.acknowledge(alert, "ana", 4.0) == [AnnounceAcknowledged(alert, "ana")]
    assert machine.state is SosState.ACKNOWLEDGED
    assert machine.acknowledge(alert, "ana", 5.0) == []
    assert machine.acknowledge(alert, "luis", 6.0) == [AnnounceAcknowledged(alert, "luis")]
    assert machine.acknowledged_by == ("ana", "luis")


def test_acknowledge_without_active_alert_is_an_error(machine):
    with pytest.raises(SosError):
        machine.acknowledge("alert-1", "ana", 1.0)


def test_acknowledge_wrong_alert_is_an_error(machine):
    trigger(machine)
    with pytest.raises(UnknownAlertError):
        machine.acknowledge("otra", "ana", 4.0)


def test_acknowledge_requires_member(machine):
    alert = trigger(machine)
    with pytest.raises(ValueError):
        machine.acknowledge(alert, "", 4.0)


def test_resolve_returns_to_idle_and_stops_alarm(machine):
    alert = trigger(machine)
    machine.acknowledge(alert, "ana", 4.0)
    effects = machine.resolve(alert, "ana", 10.0)
    assert effects == [StopLocalAlarm(alert), RecordResolved(alert, "ana")]
    assert machine.state is SosState.IDLE
    assert machine.alert_id is None
    assert machine.acknowledged_by == ()


def test_resolve_without_acknowledgement_is_allowed(machine):
    alert = trigger(machine)
    assert machine.resolve(alert, "admin", 5.0)[0] == StopLocalAlarm(alert)


def test_repeated_resolve_and_late_ack_are_ignored(machine):
    alert = trigger(machine)
    machine.resolve(alert, "ana", 5.0)
    assert machine.resolve(alert, "ana", 6.0) == []
    assert machine.acknowledge(alert, "luis", 7.0) == []
    assert machine.state is SosState.IDLE


def test_resolve_unknown_alert_is_an_error(machine):
    trigger(machine)
    with pytest.raises(UnknownAlertError):
        machine.resolve("otra", "ana", 5.0)


def test_new_alert_after_resolution_gets_new_id(machine):
    first = trigger(machine, 0.0)
    machine.release(4.0)
    machine.resolve(first, "ana", 5.0)
    second = trigger(machine, 10.0)
    assert second != first
    assert machine.state is SosState.ALERTING


def test_clock_going_backwards_is_rejected(machine):
    machine.press(10.0)
    with pytest.raises(SosError):
        machine.tick(9.0)


@pytest.mark.parametrize("hold", [0, -1])
def test_invalid_hold_seconds(hold):
    with pytest.raises(ValueError):
        SosMachine(hold_seconds=hold)


def test_default_ids_are_unique():
    m = SosMachine(hold_seconds=1)
    m.press(0)
    m.tick(1)
    first = m.alert_id
    m.resolve(first, "x", 2)
    m.press(3)
    m.tick(4)
    assert m.alert_id != first
