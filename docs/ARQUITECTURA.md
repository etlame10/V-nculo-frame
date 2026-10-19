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
| `storage.py` | SQLite local: fotos, outbox con reintentos, registro SOS | Hecho |
| `media.py` | Validación (firma, tamaño) y guardado atómico por hash | Hecho (básico) |
| `gallery` | Pase de fotos con fecha y remitente | Fase 2 |
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

## Flujo de fotografías (previsto)

1. Un familiar envía una foto al bot de Telegram.
2. La función del bot comprueba que su `telegram_user_id` está registrado y
   activo para ese marco; si no, descarta y no responde con datos.
3. Valida tipo y tamaño, guarda en el bucket privado y crea la fila `photos`.
4. La Pi sincroniza: descarga, vuelve a validar (`media.save_photo`) y
   registra en SQLite. La galería solo lee lo local.
5. Al pulsar "me gusta" se marca `liked_at` localmente y se encola el aviso
   al remitente.

## Esquema remoto (borrador, no aplicado)

Se concretará en la fase 4 como migración versionada en `supabase/migrations/`.

- `frames` (id, nombre, `device_user_id` → usuario Auth del marco)
- `frame_admins` (frame_id, user_id) — quién gestiona cada marco
- `family_members` (id, frame_id, display_name, telegram_user_id, active)
- `photos` (id, frame_id, sender_member_id, storage_path, sha256, received_at, liked_at)
- `sos_alerts` (id, frame_id, triggered_at, resolved_at, resolved_by)
- `sos_acks` (alert_id, member_id, acked_at)

Las políticas RLS se describen en [SEGURIDAD.md](SEGURIDAD.md).
