# Pruebas

## Cómo ejecutar

```bash
python -m pip install -e ".[dev,display]"
ruff check . && ruff format --check .
SDL_VIDEODRIVER=dummy pytest
```

GitHub Actions (`.github/workflows/tests.yml`) ejecuta lo mismo en cada push
y pull request, con Python 3.11 y 3.13. Sin el extra `[display]`, las pruebas
de Pillow y pygame se omiten (`pytest.importorskip`) y el resto pasa.

Base de datos remota (fase 4, D-16), sin conectarse a ningún proyecto:

```bash
./scripts/test_db.sh                 # PostgreSQL temporal + pgTAP (sin Docker; no como root)
supabase db start && supabase test db   # referencia, con la CLI oficial y Docker
```

## Cobertura actual (fases 1 a 4)

Ninguna prueba necesita red, Telegram, Supabase, hardware ni pantalla.

| Archivo | Qué comprueba |
|---|---|
| `test_sos.py` | Pulsación corta sin efecto; activación por `tick` o por `release` tardío; rebotes y pulsaciones repetidas no crean alertas ni reinician el temporizador; confirmaciones duplicadas, tardías o de alertas desconocidas; resolución idempotente; nueva alerta con nuevo id; reloj que retrocede |
| `test_sos_service.py` | Flujo completo sin Internet: alarma local inmediata, avisos que quedan en cola, registro de confirmaciones y resolución |
| `test_storage.py` | Fotos idempotentes por hash, orden, "me gusta" una sola vez; outbox con reintentos y espera exponencial; persistencia al reabrir; rechazo de esquema más nuevo y de fechas sin zona horaria; `remote_id` único, retirada y restauración, borrado que se deshace si falla el archivo |
| `test_storage_migrations.py` | BD nueva en v2 sin copia; v1→v2 conserva todo y guarda `.v1.bak`; no se repite; fallo a mitad de migración se deshace por completo (v1→v2 y v2→v3 ficticia) y el siguiente arranque funciona; BD corrupta o más nueva se rechaza sin tocarla; copia previa imposible (disco lleno) detiene la migración; copia coherente |
| `test_library.py` | Altas, duplicados (también con archivo perdido o retirado), foto rechazada, disco lleno al escribir, fallo de la BD tras escribir; borrado con y sin copia remota, archivo ausente, permiso denegado, nombre malicioso; límite, retirada de la más antigua, fotos protegidas (sin copia, con "me gusta", recientes), plan insuficiente, reserva de disco, doble comprobación en SQL; integridad (faltan, huérfanos, temporales, ajenos, dañados) y reparación conservadora con sus negativas (también con una sola foto), informe desactualizado, cuarentena que nunca sobrescribe, restauración fallida sin restos, error de disco al liberar espacio que se deshace |
| `test_media.py` | Formatos admitidos y rechazados, tamaño máximo, guardado atómico e idempotente, sin restos tras rechazo |
| `test_config.py` | Valores por defecto sin nube, validación de rangos y URL, secretos ocultos en `repr` |
| `test_gallery_playlist.py` | Galería vacía, orden más reciente primero y vuelta, desempate por id, foto única, fotos nuevas prioritarias, foto actual o pendiente borrada, fotos que fallan y reintento |
| `test_gallery_controller.py` | Bienvenida, cambio por intervalo, primera foto al refrescar, foto nueva inmediata, foto única sin recargar, error de lectura → aviso y continúa, todas rotas, error de base de datos, salto manual |
| `test_gallery_text_layout.py` | Fechas en español (Hoy, Ayer, año, reloj adelantado), zona horaria local, nombres limpios y acortados, encaje de imágenes, tamaños de letra por resolución |
| `test_gallery_imaging.py` | JPEG/PNG/WebP, reducción, orientación EXIF, PNG transparente, archivos vacíos/dañados/truncados/inexistentes, límite de píxeles, nombres que intentan salir de la carpeta |
| `test_gallery_render.py` | Foto centrada en cuatro resoluciones y orientaciones, laterales desenfocados, texto del pie, pantallas de bienvenida y error, nombre muy largo |
| `test_gallery_display.py` | Ventana con SDL sin pantalla: bienvenida, fallo de dibujo sin cerrarse, tamaño real, tecla Esc |
| `test_gallery_app.py` | Fotos ficticias a través de `PhotoLibrary`, idempotencia, vista previa, comandos `demo-photos`, `preview` y `gallery` |
| `supabase/tests/database/01_esquema.test.sql` | Solo las tablas previstas; RLS en todas; `anon` sin permisos ni políticas; políticas exactas por tabla; permisos por columna; funciones auxiliares `SECURITY DEFINER` y no ejecutables por `anon`; rutas mal formadas → `NULL`; bucket privado con formatos limitados; integridad (remitente y confirmaciones del mismo marco, ruta con el id del marco, hash y formato, foto duplicada, nombre vacío, resolución sin fecha) |
| `supabase/tests/database/02_rls.test.sql` | Con dos marcos: `anon` no lee ni escribe; usuario sin marco no ve nada; admin A ve y cambia solo lo de A (alta y desactivación de familiares, borrar fotos, resolver alertas firmando con su usuario y una sola vez), no fija `telegram_user_id`, no elige ids, no mueve ni borra familiares, no marca "me gusta"; marco A ve solo lo suyo, crea alertas (reenviar no duplica), marca "me gusta" y nada más; marco B no ve A; Storage: cada uno ve solo `<su marco>/…` |
| `test_cli.py` | `check` crea el almacenamiento, no muestra secretos y devuelve error con configuración inválida; `storage` (informe, `--deep`, `--repair` y su negativa ante un posible desmontaje), `backup` (también a un destino imposible), `delete-photo` exige `--yes`, `demo-photos --count` fuera de rango, base de datos dañada en todos los comandos sin modificarla |

## Estrategia por capas

1. **Unitarias (CI):** lógica pura con dobles (reloj, alarma, id).
2. **Integración local (CI):** SQLite real en carpetas temporales.
3. **Integración con servicios (fases 4–6):** Supabase local con su CLI y
   pruebas de políticas RLS; el bot contra respuestas simuladas de la API de
   Telegram. Ninguna prueba enviará mensajes reales.
4. **Hardware (fase 7, manual en la Pi):** `gpiozero.MockFactory` en CI y una
   lista de comprobación en el dispositivo.
5. **Aceptación (fase 9):** escenarios completos documentados abajo.

## Qué es simulación y qué falta

| Comprobado | Cómo |
|---|---|
| Lógica de la galería | Pruebas unitarias con dobles |
| Dibujo en varias resoluciones | Imágenes generadas y revisadas visualmente (vista previa PNG) |
| Ventana y bucle | SDL `dummy` en las pruebas; pantalla completa en Xvfb 1024×600 |
| **No comprobado** | Raspberry Pi 4, pantalla HDMI real, Wayland/KMS de Raspberry Pi OS, rendimiento y temperatura, legibilidad a distancia |

### Fase 3: qué se ha comprobado y cómo

| Comprobación | Resultado |
|---|---|
| Migración de bases v1 creadas por el código real de la fase 1 (`877a094`) | Datos conservados, `.v1.bak` legible, sin segunda copia al reabrir |
| Fallo simulado a mitad de la migración | Vuelve a v1 sin columnas nuevas; el siguiente arranque migra bien |
| Copia previa imposible (disco lleno simulado) | No migra y lo explica |
| Comandos `storage`, `backup`, `delete-photo`, `demo-photos` con datos ficticios | Correctos, incluidos sus errores (sin trazas de Python) |
| Errores de disco y cortes | **Simulados** (`os.replace`, `unlink` y la base de datos fallan a propósito); no probados con una tarjeta SD real ni cortando la luz |
| Concurrencia | `BEGIN IMMEDIATE` al borrar y comprobación de nuevo en `repair`; **no** probado con varios procesos reales |

Fallos encontrados en la revisión final y corregidos: `repair` con una sola
foto ante un posible desmontaje; `repair` sobre un informe desactualizado;
la cuarentena podía borrar un archivo con el mismo nombre; restauración
fallida que dejaba un archivo suelto; errores de disco al liberar espacio
como `OSError`; lectura fuera de la transacción al borrar; copia previa
fallida mostrada como "base de datos dañada"; `demo-photos --count 9` con
traza de Python; `*.bak` y la cuarentena fuera de `data/` sin ignorar en git.

### Fase 4: qué se ha comprobado y cómo

| Comprobación | Resultado |
|---|---|
| Migración + 103 pruebas pgTAP en PostgreSQL 16 con la imitación mínima | Pasan |
| Errores introducidos a propósito (política `using (true)`, sin revocar a `anon`, `UPDATE` completo en `photos`) | Las pruebas fallan en los tres casos |
| Mismas pruebas con la CLI oficial de Supabase | **Pendiente**: solo en GitHub Actions (job `supabase`) |
| Proyecto remoto | **No creado** (requiere autorización) |

Fallo encontrado al probar: la prueba de alta de familiares indicaba el `id`,
que el administrador no puede elegir; se corrigió la prueba (el permiso es el
correcto) y se añadió una prueba de que no puede elegirlo.

### Lista para la primera prueba en la Pi (fase 2, pendiente)

1. Instalar en un entorno virtual con `[display]`; `python -m vinculo_frame check`.
2. `demo-photos --with-broken` y `gallery`: ¿pantalla completa a la resolución nativa?
3. ¿Se lee el nombre y la fecha a 2–3 m? ¿El aviso de foto dañada se entiende?
4. Medir CPU y memoria con `top` durante 10 minutos.
5. Girar la pantalla (si la carcasa lo permite) y comprobar el formato vertical.

## Escenarios de aceptación previstos (fase 9)

- Desconectar la red, pulsar SOS 3 s: suena la alarma al instante; al volver
  la red, el aviso llega a todos los familiares una vez.
- Pulsación corta o rebotes en SOS: no hay alerta.
- Reiniciar la Pi con avisos pendientes: se envían tras el arranque.
- Foto de un remitente no registrado: no aparece en el marco.
- Cortar la luz durante la recepción de una foto: no queda archivo corrupto.
- 24 h de funcionamiento continuo: temperatura y memoria estables.
