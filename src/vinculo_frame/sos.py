"""Máquina de estados del botón SOS.

Es lógica pura: no lee GPIO, no habla con Telegram y no consulta el reloj.
Quien la usa le pasa eventos con una marca de tiempo monotónica (segundos,
por ejemplo ``time.monotonic()``) y ejecuta los efectos que devuelve cada
método. Así se puede probar sin hardware y reutilizar con cualquier canal
de notificación.

Estados::

    IDLE --pulsar--> HOLDING --(mantener >= hold_seconds)--> ALERTING
      ^                 |                                      |
      +---soltar antes--+                          confirmación de familiar
      |                                                        v
      +-------------------- resolver <------------------ ACKNOWLEDGED

El SOS es una función complementaria, no un servicio certificado de
emergencias.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class SosState(StrEnum):
    IDLE = "idle"
    HOLDING = "holding"
    ALERTING = "alerting"
    ACKNOWLEDGED = "acknowledged"


class SosError(Exception):
    """Evento incoherente con el estado de la máquina."""


class UnknownAlertError(SosError):
    """Se ha recibido un evento para una alerta que no es la activa."""


@dataclass(frozen=True)
class StartLocalAlarm:
    alert_id: str


@dataclass(frozen=True)
class StopLocalAlarm:
    alert_id: str


@dataclass(frozen=True)
class SendSosAlert:
    """Avisar a todos los familiares autorizados (se encola en el outbox)."""

    alert_id: str
    triggered_at: float


@dataclass(frozen=True)
class AnnounceAcknowledged:
    """Un familiar ha confirmado: mostrarlo en pantalla e informar al resto."""

    alert_id: str
    member_id: str


@dataclass(frozen=True)
class RecordResolved:
    alert_id: str
    resolved_by: str


Effect = StartLocalAlarm | StopLocalAlarm | SendSosAlert | AnnounceAcknowledged | RecordResolved

_ACTIVE_STATES = frozenset({SosState.ALERTING, SosState.ACKNOWLEDGED})


def _new_alert_id() -> str:
    return str(uuid.uuid4())


class SosMachine:
    def __init__(
        self,
        hold_seconds: float = 2.5,
        new_alert_id: Callable[[], str] = _new_alert_id,
    ) -> None:
        if hold_seconds <= 0:
            raise ValueError("hold_seconds debe ser positivo")
        self._hold_seconds = hold_seconds
        self._new_alert_id = new_alert_id
        self._state = SosState.IDLE
        self._pressed_at: float | None = None
        self._last_event_at: float | None = None
        self._alert_id: str | None = None
        self._acknowledged_by: list[str] = []
        self._resolved_ids: set[str] = set()

    @property
    def state(self) -> SosState:
        return self._state

    @property
    def alert_id(self) -> str | None:
        """Identificador de la alerta activa, o ``None`` si no hay ninguna."""
        return self._alert_id

    @property
    def acknowledged_by(self) -> tuple[str, ...]:
        return tuple(self._acknowledged_by)

    # --- Eventos del botón -------------------------------------------------

    def press(self, now: float) -> list[Effect]:
        self._advance_clock(now)
        if self._state is SosState.IDLE:
            self._state = SosState.HOLDING
            self._pressed_at = now
        # Pulsaciones repetidas o durante una alerta activa no crean otra alerta.
        return []

    def release(self, now: float) -> list[Effect]:
        self._advance_clock(now)
        if self._state is not SosState.HOLDING:
            return []
        # Si no llegó ningún tick, la duración se comprueba al soltar.
        effects = self._trigger_if_held(now)
        if not effects:
            self._state = SosState.IDLE
        self._pressed_at = None
        return effects

    def tick(self, now: float) -> list[Effect]:
        self._advance_clock(now)
        if self._state is not SosState.HOLDING:
            return []
        return self._trigger_if_held(now)

    # --- Eventos remotos o de administración -------------------------------

    def acknowledge(self, alert_id: str, member_id: str, now: float) -> list[Effect]:
        """Un familiar confirma que ha recibido el aviso."""
        self._advance_clock(now)
        if not member_id:
            raise ValueError("member_id no puede estar vacío")
        if alert_id in self._resolved_ids:
            return []  # Confirmación tardía de una alerta ya cerrada.
        self._require_active(alert_id)
        if member_id in self._acknowledged_by:
            return []
        self._acknowledged_by.append(member_id)
        self._state = SosState.ACKNOWLEDGED
        return [AnnounceAcknowledged(alert_id, member_id)]

    def resolve(self, alert_id: str, resolved_by: str, now: float) -> list[Effect]:
        """Cerrar la alerta (desde el panel o tras atender a la persona)."""
        self._advance_clock(now)
        if not resolved_by:
            raise ValueError("resolved_by no puede estar vacío")
        if alert_id in self._resolved_ids:
            return []
        self._require_active(alert_id)
        self._resolved_ids.add(alert_id)
        self._state = SosState.IDLE
        self._alert_id = None
        self._acknowledged_by = []
        return [StopLocalAlarm(alert_id), RecordResolved(alert_id, resolved_by)]

    # --- Internos ----------------------------------------------------------

    def _trigger_if_held(self, now: float) -> list[Effect]:
        assert self._pressed_at is not None
        if now - self._pressed_at < self._hold_seconds:
            return []
        alert_id = self._new_alert_id()
        self._state = SosState.ALERTING
        self._alert_id = alert_id
        self._pressed_at = None
        return [StartLocalAlarm(alert_id), SendSosAlert(alert_id, triggered_at=now)]

    def _require_active(self, alert_id: str) -> None:
        if self._state not in _ACTIVE_STATES:
            raise SosError(f"no hay ninguna alerta activa (estado {self._state})")
        if alert_id != self._alert_id:
            raise UnknownAlertError(f"la alerta {alert_id!r} no es la activa")

    def _advance_clock(self, now: float) -> None:
        if self._last_event_at is not None and now < self._last_event_at:
            raise SosError("el reloj ha retrocedido; usa un reloj monotónico")
        self._last_event_at = now
