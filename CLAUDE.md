# Vínculo Frame — guía para sesiones de Claude

Marco digital para personas mayores (Raspberry Pi 4, Python). Leer primero
`docs/PLAN.md` (fase actual) y `docs/DECISIONES_TECNICAS.md` (decisiones
pendientes que no se deben tomar sin el equipo).

## Comandos

```bash
python -m pip install -e ".[dev,display]"
ruff check . && ruff format --check .
SDL_VIDEODRIVER=dummy pytest
```

Galería: `python -m vinculo_frame demo-photos --with-broken` y después
`preview` (PNG, sin pantalla) o `gallery --windowed`. Bajo `xvfb-run` se puede
probar la pantalla completa con `--max-seconds` y `--screenshot`.

## Reglas del proyecto

- Idioma: documentación, mensajes y comentarios en español; identificadores en inglés.
- El núcleo (`sos.py`, `storage.py`, `media.py`) usa solo la biblioteca estándar.
  Pillow y pygame-ce solo en `gallery/{imaging,render,demo,display,app}.py` (extra `[display]`).
- La lógica es pura y recibe reloj/ids inyectados; GPIO, red y pantalla van en adaptadores.
- Todo aviso saliente pasa por el outbox de `LocalStore`. Nada local depende de la nube.
- Nunca: secretos reales, fotografías reales, `service_role` en la Pi o el navegador,
  puertos abiertos en la Pi, migraciones remotas o mensajes reales sin autorización.
- No inventar hardware: lo no confirmado en `docs/INVENTARIO_HARDWARE.md` no existe.
- No hay Raspberry Pi en la sesión en la nube: el hardware se prueba con dobles o `MockFactory`.
