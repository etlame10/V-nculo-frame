# Vínculo Frame

Marco digital para personas mayores. Recibe fotografías de familiares
autorizados, las muestra automáticamente y ofrece dos botones físicos:
uno para decir "la he visto y me gusta" y otro de **SOS** que avisa a la familia.

> El SOS es una función complementaria. **No** es un servicio certificado de
> emergencias ni sustituye al 112 ni a la teleasistencia.

## Estado actual (fase 5: bot de Telegram, solo en local)

| Componente | Estado |
|---|---|
| Configuración por variables de entorno (`config.py`) | Implementado y probado |
| Máquina de estados SOS, independiente de GPIO y Telegram (`sos.py`) | Implementado y probado |
| Servicio SOS: alarma local + avisos persistentes (`sos_service.py`) | Implementado y probado con dobles |
| Almacenamiento local SQLite: fotos, cola de avisos, registro SOS (`storage.py`) | Implementado y probado |
| Validación y guardado de fotografías (`media.py`) | Implementado y probado (solo firma y tamaño) |
| Galería: rotación, bienvenida, errores de lectura, varias resoluciones (`gallery/`) | Implementado y probado **en simulación** |
| Fotos ficticias y vista previa en PNG | Implementado y probado |
| Biblioteca de fotos: borrado seguro, límite de espacio, conservación, integridad (`library.py`) | Implementado y probado |
| Esquema v2 con migración transaccional y copia previa; estado de sincronización | Implementado y probado (migración real desde v1; errores de disco simulados) |
| Esquema de Supabase: tablas, RLS, permisos por columna, bucket privado (`supabase/`) | Implementado y probado en local (pgTAP); **sin proyecto remoto** |
| Bot de Telegram: vinculación con código, recepción de fotos solo de familiares, metadatos fuera (`supabase/functions/telegram-webhook/`) | Implementado y probado con Telegram simulado; **sin bot real** |
| Sincronización, botones físicos, panel web | Pendiente (fases 6 a 8) |

**Nada se ha ejecutado todavía en una Raspberry Pi ni en una pantalla física.**
La galería se ha probado con el controlador de vídeo vacío de SDL y a
pantalla completa en un servidor X virtual (Xvfb).

## Estructura

```
src/vinculo_frame/          Aplicación local (Python ≥ 3.11)
src/vinculo_frame/gallery/  Galería: lógica pura + dibujo (Pillow) + ventana (pygame)
tests/                      Pruebas automatizadas (pytest), sin hardware ni red
docs/                       Arquitectura, plan, seguridad, pruebas, decisiones, hardware
supabase/                   Migraciones SQL, pruebas pgTAP y config de la CLI de Supabase
scripts/test_db.sh          Prueba las migraciones en un PostgreSQL temporal (sin Docker)
scripts/test_functions_e2e.sh  Prueba el bot con un Supabase local (Docker), sin bot real
.github/workflows/          CI: lint, pruebas en Python 3.11 y 3.13 y pruebas de la base de datos
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

Base de datos de Supabase (no se conecta a ningún proyecto remoto):

```bash
./scripts/test_db.sh                    # requiere postgresql y postgresql-*-pgtap
supabase db start && supabase test db   # con la CLI oficial y Docker
```

Bot de Telegram (Edge Function en Deno; no envía mensajes reales):

```bash
cd supabase/functions/telegram-webhook && deno test -A
```

Puesta en marcha real (cuando el equipo lo autorice): crear el bot con
@BotFather, `supabase secrets set` con `TELEGRAM_BOT_TOKEN` y
`TELEGRAM_WEBHOOK_SECRET` (ver `supabase/functions/.env.example`),
`supabase functions deploy telegram-webhook` y registrar el webhook con
`setWebhook` y el mismo `secret_token`.

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

## Mantenimiento del almacenamiento local

```bash
python -m vinculo_frame storage            # espacio usado e integridad (código 3 si hay problemas)
python -m vinculo_frame storage --deep     # además comprueba el contenido de cada foto
python -m vinculo_frame storage --repair   # corrige solo lo seguro (ver docs/DECISIONES_TECNICAS.md, D-14)
python -m vinculo_frame backup --out copia.sqlite3
python -m vinculo_frame delete-photo --id 3 --yes
```

Límite de espacio: `VINCULO_STORAGE_LIMIT_MB` (2048 por defecto). Las fotos
recibidas en los últimos `VINCULO_KEEP_RECENT_DAYS` días (30), las que tienen
"me gusta" y las que no tienen copia remota nunca se retiran
automáticamente. Hoy ninguna foto tiene copia remota, así que al llenarse el
límite las fotos nuevas **se rechazan** en lugar de borrar nada.

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
- Hasta la fase 6 no hay copia remota: llegado el límite de espacio no se
  libera nada automáticamente y las fotos nuevas se rechazan.
- `storage --repair` es manual; ningún proceso lo ejecuta solo.
- Los fallos de disco y los cortes de luz se han probado **simulándolos**;
  no con una tarjeta SD real. Tampoco se ha probado con varios procesos
  escribiendo a la vez (lo habrá cuando exista la recepción de fotos).

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
