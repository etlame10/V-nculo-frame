# Arquitectura

## Principio rector

**El marco funciona solo.** La Raspberry Pi guarda una copia local de todo lo
que necesita (fotos, metadatos, avisos pendientes) y puede mostrar la galería
y hacer sonar la alarma SOS sin Internet. La nube sincroniza y comunica; no
es una dependencia para las funciones locales.

## Vista general

```
             Familiares (Telegram)                 Administradores (navegador)
                    │  fotos / confirmaciones SOS            │ HTTPS + login
                    ▼                                        ▼
        ┌──────────────────────┐                 ┌──────────────────────┐
        │ Telegram Bot API     │                 │ Panel web            │
        └─────────┬────────────┘                 │ (solo clave pública) │
                  │ webhook (propuesta, D-05)    └──────────┬───────────┘
                  ▼                                         │
        ┌────────────────────────────────────────────────────┴───────────┐
        │ Supabase: Postgres + RLS · Auth · Storage (bucket privado)      │
        │           Edge Function del bot (recibe y valida mensajes)      │
        └─────────────────────────────┬──────────────────────────────────┘
                                      │ solo conexiones SALIENTES desde la Pi
                                      │ (usuario "dispositivo", limitado por RLS)
        ┌─────────────────────────────┴──────────────────────────────────┐
        │ Raspberry Pi 4                                                  │
        │                                                                 │
        │  gallery ──► pantalla HDMI        buttons (gpiozero) ─┐         │
        │     ▲                                                 ▼         │
        │     │                              SosMachine (pura) ─► SosService
        │     │                                                  │  │     │
        │  LocalStore (SQLite) ◄─────────────────────────────────┘  │     │
        │   · photos  · outbox  · sos_alerts/acks                   ▼     │
        │     ▲                  │                            Alarm local │
        │     │                  ▼                                        │
        │  sync (descarga fotos) dispatcher (vacía el outbox con reintento)│
        └─────────────────────────────────────────────────────────────────┘
```

La Pi **no abre puertos** ni expone ningún servicio: todas sus conexiones
son salientes. El panel web nunca habla directamente con la Pi; ambos se
comunican a través de Supabase.

## Módulos locales

| Módulo | Responsabilidad | Estado |
|---|---|---|
| `config.py` | Leer y validar variables de entorno; ocultar secretos en `repr` | Hecho |
| `sos.py` | Máquina de estados SOS pura: recibe eventos con tiempo monotónico y devuelve efectos | Hecho |
| `sos_service.py` | Ejecuta efectos: alarma local inmediata y avisos al outbox | Hecho |
| `storage.py` | SQLite local: fotos, outbox con reintentos, registro SOS, migraciones transaccionales | Hecho |
| `library.py` | Coherencia archivo↔fila: altas, borrado, límite y conservación, integridad y reparación | Hecho |
| `media.py` | Validación (firma, tamaño) y guardado atómico por hash | Hecho (básico) |
| `gallery/playlist.py` | Orden de rotación, fotos nuevas primero, fotos que fallan (puro) | Hecho |
| `gallery/controller.py` | Qué diapositiva mostrar y cuándo; convierte errores en avisos (puro) | Hecho |
| `gallery/captions.py`, `layout.py` | Textos en español y medidas según la pantalla (puro) | Hecho |
| `gallery/imaging.py` | Lectura segura con Pillow: formatos, píxeles, orientación EXIF | Hecho |
| `gallery/render.py` | Composición de cada diapositiva como imagen (Pillow) | Hecho |
| `gallery/display.py` | Ventana a pantalla completa con pygame-ce | Hecho (sin probar en Pi) |
| `gallery/demo.py` | Fotos ficticias para pruebas | Hecho |
| `buttons` | Adaptador `gpiozero` → eventos `press/release/tick` | Fase 7 |
| `dispatcher` | Envía avisos del outbox (Telegram/Supabase) con reintento | Fase 6 |
| `sync` | Descarga fotos nuevas de Supabase Storage | Fase 6 |

## Flujo SOS

1. El adaptador de botón genera `press(t)`, `tick(t)` periódicos y `release(t)`
   con `time.monotonic()`.
2. Si se mantiene ≥ `VINCULO_SOS_HOLD_SECONDS` (2,5 s por defecto),
   `SosMachine` pasa a `ALERTING` y devuelve `StartLocalAlarm` + `SendSosAlert`.
3. `SosService` activa **primero** la alarma local y después guarda la alerta
   y un aviso en el outbox **en la misma SQLite local**. Sin Internet, el
   aviso espera; el dispatcher lo reintenta con espera exponencial (5 s … 5 min,
   sin descartarlo nunca).
4. Las confirmaciones de familiares (`acknowledge`) se registran una sola vez
   por persona y se comunican al resto.
5. `resolve` (desde el panel o un control local, por definir) apaga la
   alarma y cierra la alerta. Los eventos repetidos o tardíos se ignoran.

Estados: `IDLE → HOLDING → ALERTING → ACKNOWLEDGED → IDLE`.

## Galería (fase 2)

```
LocalStore.list_photos ──► Playlist ──► GalleryController ──► Renderer (Pillow) ──► GalleryWindow (pygame)
   (cada 30 s)              orden        diapositiva +          imagen RGB del           copia a la
                                         carga (imaging)        tamaño de la pantalla    pantalla
```

- La lógica (`playlist`, `controller`, `captions`, `layout`) no importa
  Pillow ni pygame: se prueba con dobles.
- Tres tipos de diapositiva: foto, bienvenida (sin fotos) y "no se puede
  mostrar" (8 s como máximo, y la foto se salta 5 min).
- La galería solo lee SQLite y la carpeta de fotos locales; no usa la red.
- No hay segunda base de datos ni cambios de esquema.

## Persistencia local (fase 3)

```
                     PhotoLibrary (library.py)
  add(bytes) ──► validar ──► ¿cabe? ──no──► plan de retirada ──► ¿seguro y suficiente?
                                │                                  │ no → StorageFullError
                                │ sí                               │ sí → retirar archivos
                                ▼                                  ▼       (evicted_at)
                    save_photo (atómico) ──► fila en SQLite ── si falla, se borra el archivo
```

- Toda alta, borrado o retirada pasa por `PhotoLibrary`; nadie más escribe en
  `data/photos/`.
- Borrar = una transacción: se borra la fila, se borra el archivo y, si había
  copia remota, se encola `photo_deleted`. Si el archivo no se puede borrar,
  la transacción se deshace.
- `check()` compara SQLite con la carpeta; `repair()` corrige solo lo seguro.
- Esquema v2: `photos.remote_id` (sincronización) y `photos.evicted_at`
  (archivo local retirado). Ver D-13 a D-15.

## Flujo de fotografías (pasos 1–3 en la fase 5; 4–5 en la fase 6)

```
Telegram ──POST + secret_token──► Edge Function telegram-webhook (Deno)
                                     │ handler.ts: ¿secreto? ¿chat privado? ¿familiar activo?
                                     │ telegram.ts: getFile + descarga (≤ 10 MB)
                                     │ images.ts: formato real y fuera metadatos (D-18)
                                     ▼
                     store.ts (service_role): bucket "photos" + fila photos
                                     │
Telegram ◄── respuesta en el cuerpo HTTP (sendMessage) ──┘
```

1. Un familiar envía una foto al bot de Telegram.
2. La función comprueba que su `telegram_user_id` está vinculado y activo;
   si no, responde "Este bot es privado y usted no está en la lista blanca."
   sin descargar nada.
3. Valida tipo y tamaño, quita metadatos, guarda en el bucket privado y crea
   la fila `photos` (una por marco del familiar).
4. La Pi sincroniza: descarga, reduce la resolución, vuelve a validar
   (`media.save_photo`) y registra en SQLite. La galería solo lee lo local.
5. Al pulsar "me gusta" se marca `liked_at` localmente y se encola el aviso
   al remitente.

Vinculación: el panel pide `create_link_code(familiar)` → código `XXXX-XXXX`
de un solo uso (24 h) → el familiar lo envía al bot → `redeem_link_code`
guarda su `telegram_user_id` (D-19).

## Esquema remoto (fase 4, probado en local, no aplicado en remoto)

Migración `supabase/migrations/20261102090000_esquema_inicial.sql`:

```
auth.users ◄── frames.device_user_id          (usuario del marco, D-06)
auth.users ◄── frame_admins ──► frames        (quién gestiona cada marco)
frames ◄── family_members (telegram_user_id NULL hasta vincular)
frames ◄── photos ──► family_members          (mismo marco; ruta <frame_id>/<sha256>.<ext>)
frames ◄── sos_alerts ◄── sos_acks ──► family_members   (mismo marco)
Storage: bucket privado "photos"
```

- `photos.id` es el `remote_id` de la base de datos local (D-15).
- `sos_alerts.id` lo genera el marco (uuid4 de `sos.py`): reenviar la misma
  alerta tras un corte da un conflicto de clave, no un duplicado.
- Permisos y RLS en [SEGURIDAD.md](SEGURIDAD.md); pruebas en
  [PRUEBAS.md](PRUEBAS.md).
