"""Comandos locales de Vínculo Frame.

* ``check``: comprueba la configuración y el almacenamiento sin mostrar secretos.
* ``gallery``: abre la galería (pantalla completa por defecto).
* ``demo-photos``: crea fotos ficticias para probar la galería.
* ``preview``: dibuja diapositivas como PNG, sin pantalla.

Los tres últimos necesitan el extra ``[display]`` (Pillow y pygame-ce).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import ConfigError, Settings, load_settings
from .storage import LocalStore


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
    with LocalStore(settings.database_path) as store:
        photos = create_demo_photos(
            store,
            settings.photos_dir,
            datetime.now().astimezone(),
            count=args.count,
            with_broken=args.with_broken,
            max_bytes=settings.max_photo_bytes,
        )
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

    args = parser.parse_args(argv)
    commands = {"check": lambda _: check(), "gallery": gallery}
    commands |= {"demo-photos": demo_photos, "preview": preview}
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
