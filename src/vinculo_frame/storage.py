"""Persistencia local en SQLite.

Todo lo que el marco necesita para funcionar sin Internet vive aquí:
metadatos de fotografías, avisos pendientes de enviar (outbox) y el registro
de alertas SOS con sus confirmaciones. La nube (Supabase) será una copia
sincronizada, no la fuente de la que depende el funcionamiento local.

Las fechas se guardan como texto ISO 8601 en UTC.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    mime TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    sender_name TEXT NOT NULL,
    received_at TEXT NOT NULL,
    liked_at TEXT
);
CREATE INDEX IF NOT EXISTS photos_received_at ON photos (received_at);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,
    sent_at TEXT,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS outbox_pending ON outbox (sent_at, next_attempt_at);

CREATE TABLE IF NOT EXISTS sos_alerts (
    alert_id TEXT PRIMARY KEY,
    triggered_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT
);

CREATE TABLE IF NOT EXISTS sos_acks (
    alert_id TEXT NOT NULL REFERENCES sos_alerts (alert_id),
    member_id TEXT NOT NULL,
    acked_at TEXT NOT NULL,
    PRIMARY KEY (alert_id, member_id)
);
"""


class StorageError(Exception):
    pass


@dataclass(frozen=True)
class Photo:
    id: int
    sha256: str
    file_name: str
    mime: str
    sender_id: str
    sender_name: str
    received_at: datetime
    liked_at: datetime | None


@dataclass(frozen=True)
class OutboxItem:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    next_attempt_at: datetime


@dataclass(frozen=True)
class SosRecord:
    alert_id: str
    triggered_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None
    acks: tuple[tuple[str, datetime], ...]


def backoff(attempts: int, base: float = 5.0, cap: float = 300.0) -> timedelta:
    """Espera antes del siguiente reintento: exponencial con tope (5 s ... 5 min)."""
    return timedelta(seconds=min(cap, base * 2 ** max(0, attempts - 1)))


def _ts(value: datetime) -> str:
    if value.tzinfo is None:
        raise StorageError("las fechas deben llevar zona horaria")
    # Formato de longitud fija para que la comparación de texto en SQL sea cronológica.
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


class LocalStore:
    def __init__(self, path: Path | str) -> None:
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> LocalStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._conn:
            yield self._conn

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise StorageError(f"base de datos de una versión más nueva ({version})")
        if version < SCHEMA_VERSION:
            with self._tx() as c:
                c.executescript(_SCHEMA)
                c.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # --- Fotografías -------------------------------------------------------

    def add_photo(
        self,
        *,
        sha256: str,
        file_name: str,
        mime: str,
        sender_id: str,
        sender_name: str,
        received_at: datetime,
    ) -> Photo:
        """Registra una foto. Si ya existe el mismo contenido, devuelve la existente."""
        with self._tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO photos"
                " (sha256, file_name, mime, sender_id, sender_name, received_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (sha256, file_name, mime, sender_id, sender_name, _ts(received_at)),
            )
        row = self._conn.execute("SELECT * FROM photos WHERE sha256 = ?", (sha256,)).fetchone()
        return self._photo(row)

    def list_photos(self) -> list[Photo]:
        """Fotos de la más reciente a la más antigua."""
        rows = self._conn.execute("SELECT * FROM photos ORDER BY received_at DESC, id DESC")
        return [self._photo(r) for r in rows]

    def mark_liked(self, photo_id: int, now: datetime) -> bool:
        """Marca la foto como vista y gustada. Devuelve ``False`` si ya lo estaba."""
        with self._tx() as c:
            cur = c.execute(
                "UPDATE photos SET liked_at = ? WHERE id = ? AND liked_at IS NULL",
                (_ts(now), photo_id),
            )
            if (
                cur.rowcount == 0
                and not c.execute("SELECT 1 FROM photos WHERE id = ?", (photo_id,)).fetchone()
            ):
                raise StorageError(f"no existe la foto {photo_id}")
        return cur.rowcount == 1

    @staticmethod
    def _photo(row: sqlite3.Row) -> Photo:
        return Photo(
            id=row["id"],
            sha256=row["sha256"],
            file_name=row["file_name"],
            mime=row["mime"],
            sender_id=row["sender_id"],
            sender_name=row["sender_name"],
            received_at=datetime.fromisoformat(row["received_at"]),
            liked_at=_dt(row["liked_at"]),
        )

    # --- Outbox: avisos pendientes de enviar -------------------------------

    def enqueue(self, kind: str, payload: dict[str, Any], now: datetime) -> int:
        if not kind:
            raise StorageError("kind no puede estar vacío")
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._tx() as c:
            cur = c.execute(
                "INSERT INTO outbox (kind, payload, created_at, next_attempt_at)"
                " VALUES (?, ?, ?, ?)",
                (kind, body, _ts(now), _ts(now)),
            )
        return int(cur.lastrowid)

    def due(self, now: datetime, limit: int = 20) -> list[OutboxItem]:
        """Avisos sin enviar cuyo próximo intento ya ha llegado, en orden de creación."""
        rows = self._conn.execute(
            "SELECT * FROM outbox WHERE sent_at IS NULL AND next_attempt_at <= ?"
            " ORDER BY id LIMIT ?",
            (_ts(now), limit),
        )
        return [
            OutboxItem(
                id=r["id"],
                kind=r["kind"],
                payload=json.loads(r["payload"]),
                attempts=r["attempts"],
                next_attempt_at=datetime.fromisoformat(r["next_attempt_at"]),
            )
            for r in rows
        ]

    def pending_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL").fetchone()[0]

    def mark_sent(self, item_id: int, now: datetime) -> None:
        with self._tx() as c:
            c.execute(
                "UPDATE outbox SET sent_at = ?, last_error = NULL WHERE id = ? AND sent_at IS NULL",
                (_ts(now), item_id),
            )

    def mark_failed(self, item_id: int, error: str, now: datetime) -> datetime:
        """Registra un fallo y programa el siguiente intento. Nunca se descarta."""
        row = self._conn.execute(
            "SELECT attempts FROM outbox WHERE id = ? AND sent_at IS NULL", (item_id,)
        ).fetchone()
        if row is None:
            raise StorageError(f"no hay aviso pendiente {item_id}")
        attempts = row["attempts"] + 1
        next_at = now + backoff(attempts)
        with self._tx() as c:
            c.execute(
                "UPDATE outbox SET attempts = ?, next_attempt_at = ?, last_error = ? WHERE id = ?",
                (attempts, _ts(next_at), error[:500], item_id),
            )
        return next_at

    # --- Registro de alertas SOS -------------------------------------------

    def record_sos_triggered(self, alert_id: str, at: datetime) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO sos_alerts (alert_id, triggered_at) VALUES (?, ?)",
                (alert_id, _ts(at)),
            )

    def record_sos_ack(self, alert_id: str, member_id: str, at: datetime) -> None:
        try:
            with self._tx() as c:
                c.execute(
                    "INSERT OR IGNORE INTO sos_acks (alert_id, member_id, acked_at)"
                    " VALUES (?, ?, ?)",
                    (alert_id, member_id, _ts(at)),
                )
        except sqlite3.IntegrityError as exc:
            raise StorageError(f"no existe la alerta {alert_id}") from exc

    def record_sos_resolved(self, alert_id: str, resolved_by: str, at: datetime) -> None:
        with self._tx() as c:
            cur = c.execute(
                "UPDATE sos_alerts SET resolved_at = ?, resolved_by = ?"
                " WHERE alert_id = ? AND resolved_at IS NULL",
                (_ts(at), resolved_by, alert_id),
            )
        if cur.rowcount == 0 and self.get_sos(alert_id) is None:
            raise StorageError(f"no existe la alerta {alert_id}")

    def get_sos(self, alert_id: str) -> SosRecord | None:
        row = self._conn.execute(
            "SELECT * FROM sos_alerts WHERE alert_id = ?", (alert_id,)
        ).fetchone()
        if row is None:
            return None
        acks = self._conn.execute(
            "SELECT member_id, acked_at FROM sos_acks WHERE alert_id = ? ORDER BY acked_at",
            (alert_id,),
        )
        return SosRecord(
            alert_id=row["alert_id"],
            triggered_at=datetime.fromisoformat(row["triggered_at"]),
            resolved_at=_dt(row["resolved_at"]),
            resolved_by=row["resolved_by"],
            acks=tuple((a["member_id"], datetime.fromisoformat(a["acked_at"])) for a in acks),
        )
