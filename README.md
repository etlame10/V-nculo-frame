# Vínculo Frame

Marco digital para personas mayores. Recibe fotografías de familiares
autorizados, las muestra automáticamente y ofrece dos botones físicos:
uno para decir "la he visto y me gusta" y otro de **SOS** que avisa a la familia.

> El SOS es una función complementaria. **No** es un servicio certificado de
> emergencias ni sustituye al 112 ni a la teleasistencia.

## Estado actual (fase 1: preparación y arquitectura)

| Componente | Estado |
|---|---|
| Configuración por variables de entorno (`config.py`) | Implementado y probado |
| Máquina de estados SOS, independiente de GPIO y Telegram (`sos.py`) | Implementado y probado |
| Servicio SOS: alarma local + avisos persistentes (`sos_service.py`) | Implementado y probado con dobles |
| Almacenamiento local SQLite: fotos, cola de avisos, registro SOS (`storage.py`) | Implementado y probado |
| Validación y guardado de fotografías (`media.py`) | Implementado y probado (solo firma y tamaño) |
| Diagnóstico `python -m vinculo_frame check` | Implementado y probado |
| Galería en pantalla | Pendiente (fase 2) |
| Supabase, Telegram, botones físicos, panel web | Pendiente (fases 4 a 8) |

Nada de este código se ha ejecutado todavía en una Raspberry Pi real.

## Estructura

```
src/vinculo_frame/   Código de la aplicación local (Python ≥ 3.11)
tests/               Pruebas automatizadas (pytest), sin hardware ni red
docs/                Arquitectura, plan, seguridad, pruebas, decisiones, hardware
.github/workflows/   CI: lint + pruebas en Python 3.11 y 3.13
.env.example         Plantilla de configuración con valores ficticios
```

## Uso en desarrollo

```bash
python -m pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest

cp .env.example .env          # rellenar solo en el dispositivo; nunca subir .env
python -m vinculo_frame check # comprueba configuración y crea ./data
```

`python -m vinculo_frame check` no lee `.env` por sí mismo: exporta las
variables en el entorno (en la Pi lo hará el servicio systemd, fase 9).

## Documentación

- [Arquitectura](docs/ARQUITECTURA.md)
- [Plan por fases](docs/PLAN.md)
- [Seguridad](docs/SEGURIDAD.md)
- [Pruebas](docs/PRUEBAS.md)
- [Decisiones técnicas](docs/DECISIONES_TECNICAS.md)
- [Inventario de hardware](docs/INVENTARIO_HARDWARE.md)

## Privacidad

No se suben a este repositorio fotografías reales, tokens ni datos personales.
`.gitignore` excluye `.env`, `data/` y los formatos de imagen.
