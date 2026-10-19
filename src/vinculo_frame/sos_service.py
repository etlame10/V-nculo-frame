"""Conecta la máquina SOS con la alarma local y la persistencia.

La máquina decide *qué* pasa; este servicio ejecuta los efectos:

* la alarma local se activa al instante, sin esperar a la red;
* cada aviso a familiares se guarda primero en el outbox local, de modo que
  si no hay Internet queda pendiente y se reintenta más tarde.

El envío real (Telegram, Supabase) lo hará un proceso que lea el outbox en
fases posteriores; aquí no se envía nada.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from .sos import (
    AnnounceAcknowledged,
    Effect,
    RecordResolved,
    SendSosAlert,
    SosMachine,
    StartLocalAlarm,
    StopLocalAlarm,
)
from .storage import LocalStore

OUTBOX_SOS_ALERT = "sos_alert"
OUTBOX_SOS_ACK = "sos_ack"
OUTBOX_SOS_RESOLVED = "sos_resolved"


class Alarm(Protocol):
    """Salida física de alarma (zumbador, pantalla...). En pruebas, un doble."""

    def start(self, alert_id: str) -> None: ...

    def stop(self, alert_id: str) -> None: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SosService:
    def __init__(
        self,
        machine: SosMachine,
        store: LocalStore,
        alarm: Alarm,
        wall_clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.machine = machine
        self._store = store
        self._alarm = alarm
        self._wall_clock = wall_clock

    def press(self, now: float) -> list[Effect]:
        return self._apply(self.machine.press(now))

    def release(self, now: float) -> list[Effect]:
        return self._apply(self.machine.release(now))

    def tick(self, now: float) -> list[Effect]:
        return self._apply(self.machine.tick(now))

    def acknowledge(self, alert_id: str, member_id: str, now: float) -> list[Effect]:
        return self._apply(self.machine.acknowledge(alert_id, member_id, now))

    def resolve(self, alert_id: str, resolved_by: str, now: float) -> list[Effect]:
        return self._apply(self.machine.resolve(alert_id, resolved_by, now))

    def _apply(self, effects: list[Effect]) -> list[Effect]:
        for effect in effects:
            wall = self._wall_clock()
            match effect:
                case StartLocalAlarm(alert_id):
                    self._alarm.start(alert_id)
                case StopLocalAlarm(alert_id):
                    self._alarm.stop(alert_id)
                case SendSosAlert(alert_id, _):
                    self._store.record_sos_triggered(alert_id, wall)
                    self._store.enqueue(
                        OUTBOX_SOS_ALERT,
                        {"alert_id": alert_id, "triggered_at": wall.isoformat()},
                        wall,
                    )
                case AnnounceAcknowledged(alert_id, member_id):
                    self._store.record_sos_ack(alert_id, member_id, wall)
                    self._store.enqueue(
                        OUTBOX_SOS_ACK, {"alert_id": alert_id, "member_id": member_id}, wall
                    )
                case RecordResolved(alert_id, resolved_by):
                    self._store.record_sos_resolved(alert_id, resolved_by, wall)
                    self._store.enqueue(
                        OUTBOX_SOS_RESOLVED,
                        {"alert_id": alert_id, "resolved_by": resolved_by},
                        wall,
                    )
        return effects
