"""Biblioteca de fotos local: mantiene coherentes los archivos y las filas de SQLite.

Toda foto entra, se borra o se retira a través de esta clase, de modo que no
queden archivos sin fila ni filas sin archivo.

Política de conservación
------------------------
Hay un límite de espacio para fotos (``VINCULO_STORAGE_LIMIT_MB``) y una
reserva mínima de disco libre para el sistema (``MIN_FREE_BYTES``). Si una foto
nueva no cabe, se retiran archivos locales **solo** de fotos que cumplan todo:

1. tienen copia remota (``remote_id``), así que se pueden recuperar;
2. no tienen "me gusta" de la persona mayor;
3. se recibieron hace más de ``VINCULO_KEEP_RECENT_DAYS`` días.

Se retiran primero las más antiguas y se conservan sus metadatos
(``evicted_at``). Si retirando todas las que cumplen no se libera bastante,
**no se retira ninguna**, la foto nueva no se guarda y se lanza
``StorageFullError`` para que una persona decida.

Mientras no exista la sincronización (fase 6) ninguna foto tiene copia remota,
así que la retirada automática nunca borra nada: solo avisa.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from .config import Settings
from .media import save_photo, validate_photo
from .storage import LocalStore, Photo, StorageError

MIN_FREE_BYTES = 256 * 1024 * 1024  # para el sistema operativo, registros y actualizaciones
ORPHAN_GRACE = timedelta(hours=1)  # no tocar archivos recién creados por otro proceso
PHOTO_FILE = re.compile(r"^[0-9a-f]{64}\.(jpg|png|webp)$")
TEMP_SUFFIX = ".part"  # archivos a medio escribir de media.save_photo


class StorageFullError(StorageError):
    """No hay espacio y no se puede liberar de forma segura."""


class DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


@dataclass(frozen=True)
class RetentionPolicy:
    limit_bytes: int
    keep_recent: timedelta
    min_free_bytes: int = MIN_FREE_BYTES

    @classmethod
    def from_settings(cls, settings: Settings) -> RetentionPolicy:
        return cls(settings.storage_limit_bytes, timedelta(days=settings.keep_recent_days))


@dataclass(frozen=True)
class EvictionPlan:
    needed_bytes: int  # <= 0: no hace falta liberar nada
    photos: tuple[Photo, ...]  # de la más antigua a la más reciente
    freed_bytes: int

    @property
    def sufficient(self) -> bool:
        return self.freed_bytes >= self.needed_bytes


@dataclass(frozen=True)
class Usage:
    photo_bytes: int  # todo lo que hay en la carpeta de fotos
    limit_bytes: int
    disk_free_bytes: int
    displayable: int  # fotos con archivo local
    evicted: int  # fotos retiradas por espacio (solo metadatos)
    unsynced: int  # fotos sin copia remota: nunca se retiran
    liked: int


@dataclass(frozen=True)
class IntegrityReport:
    database_errors: tuple[str, ...] = ()
    photos_dir_missing: bool = False
    missing_files: tuple[Photo, ...] = ()  # fila sin archivo
    orphan_files: tuple[Path, ...] = ()  # archivo de foto sin fila
    temp_files: tuple[Path, ...] = ()  # restos de escrituras interrumpidas
    unknown_files: tuple[Path, ...] = ()  # archivos ajenos: no se tocan
    corrupted: tuple[Photo, ...] = ()  # contenido distinto de su hash (solo con deep)

    @property
    def ok(self) -> bool:
        return not (
            self.database_errors
            or self.photos_dir_missing
            or self.missing_files
            or self.orphan_files
            or self.temp_files
            or self.corrupted
        )


@dataclass(frozen=True)
class RepairResult:
    removed_rows: int = 0  # fotos perdidas sin copia remota
    evicted_rows: int = 0  # fotos perdidas con copia remota: se podrán recuperar
    quarantined_files: int = 0
    removed_temp_files: int = 0


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class PhotoLibrary:
    def __init__(
        self,
        store: LocalStore,
        photos_dir: Path,
        policy: RetentionPolicy,
        max_photo_bytes: int,
        clock: Callable[[], datetime] = _utc_now,
        disk_usage: Callable[[Path], DiskUsage] = shutil.disk_usage,
    ) -> None:
        self._store = store
        self._photos_dir = photos_dir
        self._quarantine_dir = photos_dir.parent / "quarantine"
        self._policy = policy
        self._max_photo_bytes = max_photo_bytes
        self._clock = clock
        self._disk_usage = disk_usage

    @classmethod
    def from_settings(cls, store: LocalStore, settings: Settings) -> PhotoLibrary:
        return cls(
            store,
            settings.photos_dir,
            RetentionPolicy.from_settings(settings),
            settings.max_photo_bytes,
        )

    @property
    def quarantine_dir(self) -> Path:
        return self._quarantine_dir

    # --- Altas y bajas -----------------------------------------------------

    def add(self, data: bytes, *, sender_id: str, sender_name: str, received_at: datetime) -> Photo:
        """Valida, hace sitio si es seguro, guarda el archivo y registra la foto.

        Si el mismo contenido ya existe, devuelve la foto existente (y recupera
        su archivo si se había perdido o retirado). Si algo falla, no quedan
        ni archivo ni fila nuevos.
        """
        validate_photo(data, self._max_photo_bytes)
        digest = hashlib.sha256(data).hexdigest()
        existing = self._store.get_photo_by_sha(digest)
        if existing is not None and existing.evicted_at is None and self._file(existing).is_file():
            return existing

        self._make_room(len(data))
        try:
            saved = save_photo(self._photos_dir, data, self._max_photo_bytes)
        except OSError as exc:
            # Disco lleno, de solo lectura o dañado. save_photo ya limpia su temporal.
            raise StorageError(f"no se pudo guardar la foto en disco: {exc}") from exc

        try:
            if existing is not None:
                self._store.restore_photo(existing.id)
                restored = self._store.get_photo(existing.id)
                assert restored is not None
                return restored
            return self._store.add_photo(
                sha256=saved.sha256,
                file_name=saved.path.name,
                mime=saved.image_type.mime,
                sender_id=sender_id,
                sender_name=sender_name,
                received_at=received_at,
            )
        except BaseException:
            # Sin fila no debe quedar archivo (salvo que perteneciera a una fila existente).
            if existing is None:
                saved.path.unlink(missing_ok=True)
            raise

    def delete(self, photo_id: int) -> Photo | None:
        """Borra una foto a petición de una persona: fila, archivo y aviso a la nube."""
        return self._store.delete_photo(photo_id, self._remove_file, self._clock())

    # --- Espacio -----------------------------------------------------------

    def usage(self) -> Usage:
        photos = self._store.list_photos(include_evicted=True)
        local = [p for p in photos if p.evicted_at is None]
        return Usage(
            photo_bytes=self._photo_bytes(),
            limit_bytes=self._policy.limit_bytes,
            disk_free_bytes=self._free_bytes(),
            displayable=len(local),
            evicted=len(photos) - len(local),
            unsynced=sum(1 for p in local if not p.is_synced),
            liked=sum(1 for p in photos if p.liked_at is not None),
        )

    def plan_eviction(self, incoming_bytes: int = 0) -> EvictionPlan:
        """Qué fotos habría que retirar para que quepan ``incoming_bytes`` más."""
        needed = max(
            self._photo_bytes() + incoming_bytes - self._policy.limit_bytes,
            self._policy.min_free_bytes + incoming_bytes - self._free_bytes(),
        )
        if needed <= 0:
            return EvictionPlan(needed, (), 0)

        keep_since = self._clock() - self._policy.keep_recent
        candidates = sorted(
            (
                p
                for p in self._store.list_photos()
                if p.is_synced and p.liked_at is None and p.received_at < keep_since
            ),
            key=lambda p: (p.received_at, p.id),
        )
        chosen: list[Photo] = []
        freed = 0
        for photo in candidates:
            if freed >= needed:
                break
            chosen.append(photo)
            freed += self._file_size(photo)
        return EvictionPlan(needed, tuple(chosen), freed)

    def _make_room(self, incoming_bytes: int) -> None:
        plan = self.plan_eviction(incoming_bytes)
        if plan.needed_bytes <= 0:
            return
        if not plan.sufficient:
            raise StorageFullError(
                f"no hay espacio para la foto: faltan {plan.needed_bytes} bytes y solo se"
                f" pueden liberar {plan.freed_bytes} de forma segura; no se ha borrado nada"
            )
        now = self._clock()
        keep_since = now - self._policy.keep_recent
        for photo in plan.photos:
            self._store.evict_photo(photo.id, self._remove_file, now, keep_since)
        # Comprobar de nuevo: otra parte del programa puede haber cambiado algo.
        if self.plan_eviction(incoming_bytes).needed_bytes > 0:
            raise StorageFullError("no se ha podido liberar espacio suficiente")

    # --- Integridad --------------------------------------------------------

    def check(self, deep: bool = False) -> IntegrityReport:
        """Busca incoherencias entre SQLite y la carpeta de fotos. No modifica nada.

        ``deep`` recalcula el hash de cada archivo (lento en la Pi con muchas fotos).
        """
        database_errors = tuple(self._store.quick_check())
        rows = self._store.list_photos(include_evicted=True)
        local = {p.file_name: p for p in rows if p.evicted_at is None}

        if not self._photos_dir.is_dir():
            return IntegrityReport(
                database_errors=database_errors,
                photos_dir_missing=True,
                missing_files=tuple(local.values()),
            )

        # Las fechas de modificación vienen del sistema de archivos: se comparan con su
        # misma referencia de tiempo, no con el reloj inyectado.
        old_before = time.time() - ORPHAN_GRACE.total_seconds()
        files = {e.name: e for e in os.scandir(self._photos_dir) if e.is_file()}
        orphans, temps, unknown, corrupted = [], [], [], []
        for name, entry in sorted(files.items()):
            path = Path(entry.path)
            is_old = entry.stat().st_mtime < old_before
            if name in local:
                if deep and _sha256(path) != local[name].sha256:
                    corrupted.append(local[name])
            elif name.endswith(TEMP_SUFFIX):
                if is_old:
                    temps.append(path)
            elif PHOTO_FILE.match(name):
                if is_old:
                    orphans.append(path)
            else:
                unknown.append(path)

        return IntegrityReport(
            database_errors=database_errors,
            missing_files=tuple(p for name, p in local.items() if name not in files),
            orphan_files=tuple(orphans),
            temp_files=tuple(temps),
            unknown_files=tuple(unknown),
            corrupted=tuple(corrupted),
        )

    def repair(self, report: IntegrityReport) -> RepairResult:
        """Corrige lo que ``check`` encontró, sin perder nada recuperable.

        * Archivos sin fila → se mueven a ``quarantine/`` (pueden ser fotos reales
          si se restauró una base de datos antigua); no se borran.
        * Temporales de escrituras interrumpidas → se borran.
        * Filas sin archivo → si hay copia remota se marcan como retiradas (se
          podrán recuperar); si no, la foto ya se perdió y se borra la fila.
        * Archivos dañados (``deep``) → solo se informa.

        Se niega a actuar si parece un problema de montaje (falta la carpeta o
        faltan todos los archivos), o si SQLite informa de daños.
        """
        if report.database_errors:
            raise StorageError("la base de datos tiene errores de integridad; no se repara")
        if report.photos_dir_missing and report.missing_files:
            raise StorageError("no se encuentra la carpeta de fotos; ¿tarjeta o disco desmontado?")
        displayable = len(self._store.list_photos())
        if displayable > 1 and len(report.missing_files) == displayable:
            raise StorageError(
                "faltan los archivos de todas las fotos; ¿tarjeta o disco desmontado?"
                " No se ha modificado nada"
            )

        now = self._clock()
        removed = evicted = 0
        for photo in report.missing_files:
            if photo.is_synced:
                self._store.mark_file_missing(photo.id, now)
                evicted += 1
            elif self._store.delete_photo(photo.id, lambda _: None, now) is not None:
                removed += 1

        quarantined = 0
        for path in report.orphan_files:
            self._quarantine_dir.mkdir(parents=True, exist_ok=True)
            target = self._quarantine_dir / path.name
            if target.exists():
                path.unlink(missing_ok=True)  # mismo nombre = mismo contenido (hash)
            else:
                os.replace(path, target)
            quarantined += 1

        temps = 0
        for path in report.temp_files:
            path.unlink(missing_ok=True)
            temps += 1
        return RepairResult(removed, evicted, quarantined, temps)

    # --- Internos ----------------------------------------------------------

    def _file(self, photo: Photo) -> Path:
        if not PHOTO_FILE.match(photo.file_name):
            # Nunca se borra ni se lee una ruta que no hayamos creado nosotros.
            raise StorageError(f"nombre de archivo inesperado: {photo.file_name!r}")
        return self._photos_dir / photo.file_name

    def _remove_file(self, photo: Photo) -> None:
        self._file(photo).unlink(missing_ok=True)

    def _file_size(self, photo: Photo) -> int:
        try:
            return self._file(photo).stat().st_size
        except OSError:
            return 0

    def _photo_bytes(self) -> int:
        if not self._photos_dir.is_dir():
            return 0
        return sum(e.stat().st_size for e in os.scandir(self._photos_dir) if e.is_file())

    def _free_bytes(self) -> int:
        path = self._photos_dir
        while not path.exists() and path != path.parent:
            path = path.parent
        return self._disk_usage(path).free
