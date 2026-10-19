"""Configuración leída de variables de entorno.

La aplicación local solo necesita los valores de la sección "local" para
funcionar. Las credenciales de Telegram y Supabase son opcionales: si faltan,
las integraciones remotas quedan desactivadas y el marco sigue funcionando
sin conexión.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


class ConfigError(ValueError):
    """Valor de configuración ausente o no válido."""


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    slide_seconds: float = 15.0
    sos_hold_seconds: float = 2.5
    max_photo_bytes: int = 10 * 1024 * 1024
    log_level: str = "INFO"
    # repr=False evita que los secretos aparezcan en logs o trazas.
    telegram_bot_token: str | None = field(default=None, repr=False)
    supabase_url: str | None = None
    # Clave pública (anon/publishable): solo da lo que permitan las políticas RLS.
    supabase_anon_key: str | None = None
    # El marco inicia sesión como un usuario propio, limitado por RLS a su marco.
    # Nunca se usa la clave service_role en el dispositivo.
    supabase_device_email: str | None = None
    supabase_device_password: str | None = field(default=None, repr=False)
    device_id: str | None = None

    @property
    def database_path(self) -> Path:
        return self.data_dir / "vinculo.sqlite3"

    @property
    def photos_dir(self) -> Path:
        return self.data_dir / "photos"

    @property
    def telegram_enabled(self) -> bool:
        return self.telegram_bot_token is not None

    @property
    def supabase_enabled(self) -> bool:
        return None not in (
            self.supabase_url,
            self.supabase_anon_key,
            self.supabase_device_email,
            self.supabase_device_password,
        )


def _optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _float(env: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = _optional(env, name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} debe ser un número, no {raw!r}") from exc
    if not low <= value <= high:
        raise ConfigError(f"{name} debe estar entre {low} y {high}, no {value}")
    return value


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Construye la configuración a partir de ``env`` (por defecto, ``os.environ``)."""
    env = os.environ if env is None else env

    log_level = (_optional(env, "VINCULO_LOG_LEVEL") or "INFO").upper()
    if log_level not in LOG_LEVELS:
        raise ConfigError(f"VINCULO_LOG_LEVEL debe ser uno de {sorted(LOG_LEVELS)}")

    supabase_url = _optional(env, "SUPABASE_URL")
    if supabase_url is not None and not supabase_url.startswith("https://"):
        raise ConfigError("SUPABASE_URL debe usar https://")

    max_photo_mb = _float(env, "VINCULO_MAX_PHOTO_MB", 10.0, 0.1, 50.0)

    return Settings(
        data_dir=Path(_optional(env, "VINCULO_DATA_DIR") or "./data"),
        slide_seconds=_float(env, "VINCULO_SLIDE_SECONDS", 15.0, 3.0, 3600.0),
        sos_hold_seconds=_float(env, "VINCULO_SOS_HOLD_SECONDS", 2.5, 1.0, 10.0),
        max_photo_bytes=int(max_photo_mb * 1024 * 1024),
        log_level=log_level,
        telegram_bot_token=_optional(env, "TELEGRAM_BOT_TOKEN"),
        supabase_url=supabase_url,
        supabase_anon_key=_optional(env, "SUPABASE_ANON_KEY"),
        supabase_device_email=_optional(env, "SUPABASE_DEVICE_EMAIL"),
        supabase_device_password=_optional(env, "SUPABASE_DEVICE_PASSWORD"),
        device_id=_optional(env, "VINCULO_DEVICE_ID"),
    )
