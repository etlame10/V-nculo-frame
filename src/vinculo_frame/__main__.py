"""Diagnóstico local: ``python -m vinculo_frame check``.

Carga la configuración, crea la base de datos local si no existe e informa
del estado sin mostrar ningún secreto.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import ConfigError, load_settings
from .storage import LocalStore


def check() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuración no válida: {exc}", file=sys.stderr)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vinculo_frame")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="comprobar configuración y almacenamiento local")
    args = parser.parse_args(argv)
    if args.command == "check":
        return check()
    return 1  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
