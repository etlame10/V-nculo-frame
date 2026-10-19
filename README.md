# Vínculo Frame

Marco digital para personas mayores. Recibe fotografías de familiares
autorizados, las muestra automáticamente y ofrece dos botones físicos:
uno para decir "la he visto y me gusta" y otro de **SOS** que avisa a la familia.

> El SOS es una función complementaria. **No** es un servicio certificado de
> emergencias ni sustituye al 112 ni a la teleasistencia.

## Estado actual (fase 2: galería local)

| Componente | Estado |
|---|---|
| Configuración por variables de entorno (`config.py`) | Implementado y probado |
| Máquina de estados SOS, independiente de GPIO y Telegram (`sos.py`) | Implementado y probado |
| Servicio SOS: alarma local + avisos persistentes (`sos_service.py`) | Implementado y probado con dobles |
| Almacenamiento local SQLite: fotos, cola de avisos, registro SOS (`storage.py`) | Implementado y probado |
| Validación y guardado de fotografías (`media.py`) | Implementado y probado (solo firma y tamaño) |
| Galería: rotación, bienvenida, errores de lectura, varias resoluciones (`gallery/`) | Implementado y probado **en simulación** |
| Fotos ficticias y vista previa en PNG | Implementado y probado |
| Supabase, Telegram, botones físicos, panel web | Pendiente (fases 4 a 8) |

**Nada se ha ejecutado todavía en una Raspberry Pi ni en una pantalla física.**
La galería se ha probado con el controlador de vídeo vacío de SDL y a
pantalla completa en un servidor X virtual (Xvfb).

## Estructura

```
src/vinculo_frame/          Aplicación local (Python ≥ 3.11)
src/vinculo_frame/gallery/  Galería: lógica pura + dibujo (Pillow) + ventana (pygame)
tests/                      Pruebas automatizadas (pytest), sin hardware ni red
docs/                       Arquitectura, plan, seguridad, pruebas, decisiones, hardware
.github/workflows/          CI: lint + pruebas en Python 3.11 y 3.13
.env.example                Plantilla de configuración con valores ficticios
```

## Instalación para desarrollo

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -e ".[dev,display]"   # [display] = Pillow + pygame-ce
ruff check . && ruff format --check .
SDL_VIDEODRIVER=dummy pytest                 # sin pantalla física
```

Sin el extra `[display]` el núcleo sigue funcionando y sus pruebas pasan;
las de la galería se omiten.

## Probar la galería

Todos los comandos leen la configuración de variables de entorno
(`VINCULO_DATA_DIR`, `VINCULO_SLIDE_SECONDS`…; ver `.env.example`). No leen
`.env` por sí mismos.

```bash
export VINCULO_DATA_DIR=./data

python -m vinculo_frame demo-photos --with-broken   # 6 fotos ficticias + 1 dañada
python -m vinculo_frame preview --size 1080x1920 --slides 7   # PNG en ./preview, sin pantalla
python -m vinculo_frame gallery --windowed          # ventana de 1280×720
python -m vinculo_frame gallery                     # pantalla completa
python -m vinculo_frame check                       # estado de configuración y datos
```

Teclas (solo para desarrollo): **Esc** o **Q** salir; **→** o **espacio**
pasar a la siguiente foto. Opciones útiles de `gallery`: `--size ANCHOxALTO`,
`--max-seconds N` y `--screenshot archivo.png`.

Las fotos ficticias son paisajes dibujados por el programa, con remitentes
inventados; se guardan en `VINCULO_DATA_DIR`, que git ignora.

### En la Raspberry Pi (pendiente de verificar)

Previsto para Raspberry Pi OS (Bookworm o posterior) con Python 3.11+:
instalar en un entorno virtual con `pip install -e ".[display]"` (el Pillow
de `apt` en Bookworm es anterior a 10.1, la versión mínima) y tener
`fonts-dejavu-core`. Con escritorio, SDL usa Wayland/X11; sin escritorio
puede probarse `SDL_VIDEODRIVER=kmsdrm`. El arranque automático y el
apagado del salvapantallas se resolverán en la fase 9.

## Limitaciones conocidas

- No probado en Raspberry Pi, en pantalla HDMI real ni con pantallas táctiles.
- Rendimiento medido solo en la máquina de la nube (≈ 26 ms leer y ≈ 80 ms
  dibujar una foto a 1920×1080); en la Pi 4 será más lento y está por medir.
- Los metadatos EXIF se usan para orientar la foto pero **no se eliminan**
  del archivo guardado; se hará al recibir fotos (fase 5).
- Las fechas usan la hora del sistema; la Pi 4 no tiene reloj propio y, sin
  red tras un corte, la hora puede ser incorrecta (ver INVENTARIO_HARDWARE.md).
- Sin transiciones entre fotos (decisión deliberada: evitar animaciones).

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
