# Plan por fases

Cada fase termina cuando sus pruebas de aceptación pasan en CI (o, si
dependen del hardware, en la Pi con el resultado anotado). "HW" indica qué
hardware hace falta; las fases sin hardware se pueden hacer íntegramente
desde Claude en la nube.

## 1. Preparación y arquitectura — *completada en esta sesión*
- **Objetivos:** estructura del repositorio, documentación, configuración,
  máquina SOS, almacenamiento local, CI.
- **Archivos:** `pyproject.toml`, `.gitignore`, `.env.example`,
  `src/vinculo_frame/{config,sos,sos_service,storage,media,__main__}.py`,
  `tests/`, `docs/`, `.github/workflows/tests.yml`.
- **Aceptación:** `ruff` y `pytest` en verde en Python 3.11 y 3.13. ✔ (local)
- **HW:** ninguno.

## 2. Galería local
- **Objetivos:** pase de fotos a pantalla completa desde `LocalStore`, con
  fecha y nombre del remitente en letra grande; pantalla de "aún no hay
  fotos"; limpieza de EXIF y redimensionado al recibir; elegir librería (D-09).
- **Archivos:** `gallery/playlist.py` (orden y rotación, lógica pura),
  `gallery/render.py` (dibujo), `media.py` (decodificación, EXIF, límite de
  píxeles), extra opcional `[display]` en `pyproject.toml`.
- **Aceptación:** pruebas de la lista de reproducción (orden, foto nueva
  prioritaria, rotación, lista vacía); render a imagen en memoria en CI;
  foto con EXIF GPS sale sin él; imagen de 20 000×20 000 rechazada.
- **HW:** ninguno para la lógica; la pantalla real para validar legibilidad.

## 3. Persistencia local
- **Objetivos:** completar `storage.py`: borrado de fotos (archivo + fila),
  límite de espacio con política de retención, marca de sincronización,
  migración v1→v2, copia de seguridad sencilla.
- **Archivos:** `storage.py`, `media.py`, `tests/test_storage.py`.
- **Aceptación:** migración desde una BD v1 conserva datos; corte simulado a
  mitad de escritura no corrompe; al superar el límite se borran las más
  antiguas ya sincronizadas, nunca las pendientes.
- **HW:** ninguno.

## 4. Supabase: esquema y permisos
- **Objetivos:** migraciones SQL versionadas y políticas RLS (SEGURIDAD.md);
  bucket privado; usuario dispositivo (D-06).
- **Archivos:** `supabase/migrations/*.sql`, `supabase/tests/*.sql` (pgTAP),
  `supabase/config.toml`.
- **Aceptación:** con Supabase local (CLI + Docker en CI): `anon` no lee nada;
  admin de A no ve B; dispositivo A no ve B ni puede borrar familiares.
- **HW:** ninguno. **Requiere autorización** para crear el proyecto
  remoto y aplicar migraciones (no se hará sin permiso explícito).
- **Decisiones previas:** D-07, D-12 (región y retención).

## 5. Telegram y autorización de familiares
- **Objetivos:** recibir fotos solo de familiares registrados; vinculación
  segura (código de un solo uso generado desde el panel); respuestas claras
  al remitente; nada de Messenger.
- **Archivos:** `supabase/functions/telegram-webhook/` o `src/vinculo_frame/telegram/`
  según D-05; pruebas con respuestas simuladas de la API.
- **Aceptación:** remitente no registrado → rechazado sin almacenar; foto
  válida → fila + archivo; archivo no imagen o demasiado grande → rechazado;
  webhook sin `secret_token` correcto → 401; código de vinculación caducado o
  reutilizado → rechazado.
- **HW:** ninguno. **Requiere** crear un bot de pruebas (lo hace el equipo;
  el token nunca se sube al repositorio).
- **Decisión previa:** D-05.

## 6. Sincronización y confirmaciones
- **Objetivos:** `sync` descarga fotos nuevas; `dispatcher` vacía el outbox
  (SOS, confirmaciones, "me gusta") con reintentos e idempotencia; recibir
  confirmaciones SOS de familiares y aplicarlas a `SosService`.
- **Archivos:** `sync.py`, `dispatcher.py`, `notifier.py` (interfaz +
  implementación Telegram), pruebas con dobles de red.
- **Aceptación:** sin red se acumulan avisos y al volver se envían una vez
  cada uno; fallo a mitad no duplica la foto local; confirmación de alerta
  desconocida se registra y se ignora.
- **HW:** ninguno.

## 7. Botones físicos y SOS
- **Objetivos:** adaptador `gpiozero` → `press/release/tick`; botón "me
  gusta" sobre la foto actual; salida de alarma; servicio systemd.
- **Archivos:** `buttons.py`, `alarm.py`, `deploy/vinculo-frame.service`,
  `docs/INVENTARIO_HARDWARE.md` (pines).
- **Aceptación:** en CI con `MockFactory`: rebotes, pulsación de 2,5 s,
  pulsación larga del botón equivocado. En la Pi: lista de comprobación
  manual firmada con fecha.
- **HW:** **imprescindible**: Pi, pulsadores, zumbador; inventario y
  verificación eléctrica (3,3 V) antes de cablear.
- **Decisión previa:** D-08 y cómo se resuelve un SOS localmente.

## 8. Panel web
- **Objetivos:** inicio de sesión; gestión de familiares y vinculación;
  fotos (ver, borrar); estadísticas (fotos por remitente, "me gusta");
  historial y resolución de alertas.
- **Archivos:** `web/` (tecnología según D-11).
- **Aceptación:** sin sesión no se ve nada; un admin solo ve su marco; en el
  bundle del navegador no aparece ninguna clave `service_role` (comprobación
  automática en CI).
- **HW:** ninguno. **Requiere** decisión de alojamiento (coste).

## 9. Pruebas integrales y montaje
- **Objetivos:** escenarios de aceptación de PRUEBAS.md; arranque automático;
  actualización segura desde GitHub; montaje en carcasa; prueba de 24 h.
- **Archivos:** `deploy/`, `docs/INSTALACION.md`, `docs/PRUEBAS.md`.
- **HW:** **imprescindible**: equipo completo montado.

## 10. Evaluación de Facebook Messenger
- **Objetivos:** estudiar requisitos de la plataforma (revisión de la app,
  políticas de mensajería, coste), privacidad y si encaja en la interfaz
  `notifier`. Solo documento de evaluación; implementar únicamente si se
  aprueba.
- **HW:** ninguno.

## Dependencias entre fases

```
1 ─► 2 ─► 3 ─► 4 ─► 5 ─► 6 ─► 7 ─► 8 ─► 9 ─► 10
                     └──────────► 8 (el panel solo necesita 4 y 5)
1 ─► 7 (la lógica de botones con MockFactory puede adelantarse)
```
