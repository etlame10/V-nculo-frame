"""Comandos locales de Vínculo Frame.

* ``check``: comprueba la configuración y el almacenamiento sin mostrar secretos.
* ``gallery``: abre la galería (pantalla completa por defecto).
* ``demo-photos``: crea fotos ficticias para probar la galería.
* ``preview``: dibuja diapositivas como PNG, sin pantalla.
* ``storage``: espacio usado e integridad; ``--repair`` corrige lo que es seguro.
* ``backup``: copia coherente de la base de datos.
* ``delete-photo``: borra una foto (archivo, fila y aviso a la nube).

``gallery``, ``demo-photos`` y ``preview`` necesitan el extra ``[display]`` (Pillow y pygame-ce).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import ConfigError, Settings, load_settings
from .library import IntegrityReport, PhotoLibrary
from .storage import LocalStore, StorageError


def _settings() -> Settings | None:
    try:
        return load_settings()
    except ConfigError as exc:
        print(f"Configuración no válida: {exc}", file=sys.stderr)
        return None


def check() -> int:
    settings = _settings()
    if settings is None:
        return 2

    settings.photos_dir.mkdir(parents=True, exist_ok=True)
    with LocalStore(settings.database_path) as store:
        photos = len(store.list_photos())
        pending = store.pending_count()

    def on_off(enabled: bool) -> str:
        return "configurado" if enabled else "no configurado"

    print(f"Vínculo Frame {__version__}")
    print(f"  Datos locales:   {settings.data_dir.resolve()}")
    print(f"  Fotografías:     {photos}")
    print(f"  Avisos en cola:  {pending}")
    print(f"  Pase de fotos:   {settings.slide_seconds:g} s")
    print(f"  SOS (mantener):  {settings.sos_hold_seconds:g} s")
    print(f"  Telegram:        {on_off(settings.telegram_enabled)}")
    print(f"  Supabase:        {on_off(settings.supabase_enabled)}")
    return 0


def gallery(args: argparse.Namespace) -> int:
    from .gallery.app import run_gallery

    settings = _settings()
    if settings is None:
        return 2
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
    run_gallery(
        settings,
        size=args.size,
        fullscreen=not args.windowed,
        max_seconds=args.max_seconds,
        screenshot=args.screenshot,
    )
    return 0


def demo_photos(args: argparse.Namespace) -> int:
    from .gallery.demo import create_demo_photos

    settings = _settings()
    if settings is None:
        return 2
    try:
        with LocalStore(settings.database_path) as store:
            photos = create_demo_photos(
                PhotoLibrary.from_settings(store, settings),
                datetime.now().astimezone(),
                count=args.count,
                with_broken=args.with_broken,
            )
    except StorageError as exc:
        print(f"No se han podido crear las fotos: {exc}", file=sys.stderr)
        return 1
    print(f"{len(photos)} fotos ficticias en {settings.photos_dir.resolve()}")
    return 0


def preview(args: argparse.Namespace) -> int:
    from .gallery.app import render_previews

    settings = _settings()
    if settings is None:
        return 2
    paths = render_previews(settings, args.out, args.size, args.slides, datetime.now().astimezone())
    for path in paths:
        print(path)
    return 0


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.1f} MB"


def storage(args: argparse.Namespace) -> int:
    settings = _settings()
    if settings is None:
        return 2
    try:
        with LocalStore(settings.database_path) as store:
            library = PhotoLibrary.from_settings(store, settings)
            usage = library.usage()
            report = library.check(deep=args.deep)
            print(f"Esquema de la base de datos: v{store.schema_version}")
            print(f"Espacio de fotos: {_mb(usage.photo_bytes)} de {_mb(usage.limit_bytes)}")
            print(f"Disco libre:      {_mb(usage.disk_free_bytes)}")
            print(f"Fotos en pantalla: {usage.displayable} (sin copia remota: {usage.unsynced})")
            print(f"Fotos retiradas por espacio: {usage.evicted}; con 'me gusta': {usage.liked}")
            _print_report(report)
            if args.repair and not report.ok:
                result = library.repair(report)
                print(
                    f"Reparado: {result.removed_rows} filas sin archivo borradas,"
                    f" {result.evicted_rows} marcadas para recuperar,"
                    f" {result.quarantined_files} archivos a {library.quarantine_dir},"
                    f" {result.removed_temp_files} temporales borrados"
                )
                return 0
    except (StorageError, OSError) as exc:
        print(f"Error de almacenamiento: {exc}", file=sys.stderr)
        return 1
    return 0 if report.ok else 3


def _print_report(report: IntegrityReport) -> None:
    if report.ok and not report.unknown_files:
        print("Integridad: correcta")
        return
    findings = [
        ("Errores de SQLite", report.database_errors),
        ("Fotos sin archivo", [p.id for p in report.missing_files]),
        ("Archivos sin foto", [p.name for p in report.orphan_files]),
        ("Temporales antiguos", [p.name for p in report.temp_files]),
        ("Archivos dañados", [p.id for p in report.corrupted]),
        ("Archivos ajenos (no se tocan)", [p.name for p in report.unknown_files]),
    ]
    if report.photos_dir_missing:
        print("Integridad: NO se encuentra la carpeta de fotos")
    for label, items in findings:
        if items:
            print(f"  {label}: {len(items)} → {', '.join(map(str, items[:5]))}")


def backup(args: argparse.Namespace) -> int:
    settings = _settings()
    if settings is None:
        return 2
    try:
        with LocalStore(settings.database_path) as store:
            store.backup(args.out)
    except (StorageError, OSError) as exc:
        print(f"No se ha podido hacer la copia: {exc}", file=sys.stderr)
        return 1
    print(f"Copia guardada en {args.out}")
    return 0


def delete_photo(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Borrar es irreversible para esta copia local. Repite con --yes.", file=sys.stderr)
        return 2
    settings = _settings()
    if settings is None:
        return 2
    try:
        with LocalStore(settings.database_path) as store:
            photo = PhotoLibrary.from_settings(store, settings).delete(args.id)
    except StorageError as exc:
        print(f"No se ha podido borrar: {exc}", file=sys.stderr)
        return 1
    if photo is None:
        print(f"No existe la foto {args.id}", file=sys.stderr)
        return 1
    print(f"Foto {photo.id} borrada")
    return 0


def _size(text: str) -> tuple[int, int]:
    from .gallery.layout import parse_size

    try:
        return parse_size(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vinculo_frame")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="comprobar configuración y almacenamiento local")

    p = sub.add_parser("gallery", help="mostrar la galería")
    p.add_argument("--windowed", action="store_true", help="ventana en lugar de pantalla completa")
    p.add_argument("--size", type=_size, help="ANCHOxALTO; por defecto, la pantalla entera")
    p.add_argument("--max-seconds", type=float, help="cerrar tras N segundos (pruebas)")
    p.add_argument("--screenshot", help="guardar la última imagen mostrada en este PNG")

    p = sub.add_parser("demo-photos", help="crear fotos ficticias de prueba")
    p.add_argument("--count", type=int, default=6, help="número de fotos (1-6)")
    p.add_argument("--with-broken", action="store_true", help="añadir una foto dañada")

    p = sub.add_parser("preview", help="dibujar diapositivas como PNG, sin pantalla")
    p.add_argument("--out", type=Path, default=Path("preview"), help="carpeta de salida")
    p.add_argument("--size", type=_size, default=(1920, 1080), help="ANCHOxALTO")
    p.add_argument("--slides", type=int, default=3, help="número de diapositivas")

    p = sub.add_parser("storage", help="espacio e integridad del almacenamiento local")
    p.add_argument("--repair", action="store_true", help="corregir lo que es seguro corregir")
    p.add_argument("--deep", action="store_true", help="comprobar el contenido de cada foto")

    p = sub.add_parser("backup", help="copia de la base de datos local")
    p.add_argument("--out", type=Path, required=True, help="archivo de destino")

    p = sub.add_parser("delete-photo", help="borrar una foto")
    p.add_argument("--id", type=int, required=True, help="identificador de la foto")
    p.add_argument("--yes", action="store_true", help="confirmar el borrado")

    args = parser.parse_args(argv)
    commands = {"check": lambda _: check(), "gallery": gallery}
    commands |= {"demo-photos": demo_photos, "preview": preview, "storage": storage}
    commands |= {"backup": backup, "delete-photo": delete_photo}
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
