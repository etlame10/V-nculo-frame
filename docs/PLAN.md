# Plan por fases

Cada fase termina cuando sus pruebas de aceptación pasan en CI (o, si
dependen del hardware, en la Pi con el resultado anotado). "HW" indica qué
hardware hace falta; las fases sin hardware se pueden hacer íntegramente
desde Claude en la nube.

## 1. Preparación y arquitectura — *completada*
- **Objetivos:** estructura del repositorio, documentación, configuración,
  máquina SOS, almacenamiento local, CI.
- **Archivos:** `pyproject.toml`, `.gitignore`, `.env.example`,
  `src/vinculo_frame/{config,sos,sos_service,storage,media,__main__}.py`,
  `tests/`, `docs/`, `.github/workflows/tests.yml`.
- **Aceptación:** `ruff` y `pytest` en verde en Python 3.11 y 3.13. ✔ (local y GitHub Actions, commit `47b8ab7`)
- **HW:** ninguno.

## 2. Galería local — *completada en simulación; pendiente de validar en la Pi*
- **Objetivos:** pase de fotos a pantalla completa desde `LocalStore`, con
  fecha y nombre del remitente en letra grande; pantalla de bienvenida sin
  fotos; aviso comprensible si una foto no se puede leer; adaptación a
  resoluciones y orientaciones; fotos ficticias para probar.
- **Tecnología (D-09):** pygame-ce para la ventana y Pillow para decodificar
  y componer, en el extra opcional `[display]`.
- **Archivos:** `gallery/playlist.py`, `gallery/controller.py`,
  `gallery/captions.py`, `gallery/layout.py` (lógica pura);
  `gallery/imaging.py`, `gallery/render.py`, `gallery/demo.py` (Pillow);
  `gallery/display.py` (pygame); `gallery/app.py`; comandos `gallery`,
  `demo-photos` y `preview` en `__main__.py`. Sin cambios en el esquema de
  SQLite: se usa la tabla `photos` existente.
- **Aceptación:**
  - ✔ Orden de rotación (más reciente primero, vuelta al principio), foto
    nueva prioritaria, foto borrada, galería vacía, fotos que fallan.
  - ✔ Errores de lectura (archivo inexistente, truncado, formato no admitido,
    nombre de archivo malicioso, imagen de demasiados píxeles) → aviso en
    pantalla y la galería continúa; error de la base de datos → se siguen
    mostrando las fotos ya cargadas.
  - ✔ Orientación EXIF aplicada; dibujo correcto en 1920×1080, 1080×1920,
    800×480 y 1024×600.
  - ✔ Ventana probada con SDL sin pantalla y a pantalla completa en Xvfb.
  - ✘ Pendiente: legibilidad y rendimiento en la pantalla real con la Pi 4.
- **Cambio respecto al plan inicial:** la eliminación de EXIF y la
  recompresión al recibir pasan a la fase 5 (recepción), porque `media.py`
  debe seguir usando solo la biblioteca estándar.
- **HW:** ninguno para la lógica; la pantalla real para validar legibilidad.

## 3. Persistencia local — *completada en simulación; pendiente de validar en la Pi*
- **Objetivos:** borrado seguro de fotos (archivo + fila), límite de espacio
  con política de conservación explícita, estado de sincronización,
  migración v1→v2 transaccional, integridad, reparación y copia de seguridad.
- **Archivos:** `library.py` (nuevo: coordina archivos y filas, política
  D-14), `storage.py` (migraciones D-13, columnas D-15, borrado y retirada
  atómicos), `config.py`, `gallery/demo.py` (usa `PhotoLibrary.add`),
  comandos `storage`, `backup` y `delete-photo`.
- **Migración aplicada:** v1 → v2 añade `photos.remote_id` (único) y
  `photos.evicted_at`. Copia previa automática `*.v1.bak`.
- **Aceptación:**
  - ✔ Migración desde una BD v1 (creada con el código real de la fase 1)
    conserva fotos, "me gusta", avisos y SOS; un fallo a mitad de la
    migración la deshace por completo y el siguiente arranque migra bien.
  - ✔ Corte simulado al escribir (`os.replace` falla, interrupción antes
    de registrar): no quedan archivos ni filas a medias.
  - ✔ Al superar el límite solo se retiran fotos con copia remota, sin
    "me gusta" y antiguas, de la más antigua a la más reciente; si no basta,
    no se retira ninguna y la foto nueva se rechaza.
  - ✔ Errores de disco, archivos ausentes, huérfanos, temporales, duplicados,
    archivos dañados y base de datos corrupta: detectados y tratados sin
    pérdidas evitables.
  - ✔ Galería (fase 2) y SOS (fase 1) sin regresiones: 217 pruebas en
    Python 3.11 y 3.13; galería a pantalla completa en Xvfb con datos
    creados por `PhotoLibrary`.
  - ✔ Revisión final: corregidos 9 fallos encontrados al revisar (ver
    PRUEBAS.md), cada uno con su prueba.
  - ✔ GitHub Actions en verde (commit `fa33e07`).
  - ✘ Sin probar: tarjeta SD real, cortes de luz reales, varios procesos
    escribiendo a la vez y rendimiento de `storage --deep` en la Pi.
- **Pendiente:** fijar el límite real según la tarjeta SD (inventario) y las
  decisiones legales de D-12. La retirada automática no actuará hasta la fase 6.
- **HW:** ninguno.

## 4. Supabase: esquema y permisos — *completada en local; sin proyecto remoto*
- **Objetivos:** migraciones SQL versionadas y políticas RLS (SEGURIDAD.md);
  bucket privado; usuario dispositivo (D-06).
- **Archivos:** `supabase/config.toml` (generado con `supabase init`),
  `supabase/migrations/20261102090000_esquema_inicial.sql`,
  `supabase/tests/database/*.test.sql` (pgTAP), `scripts/test_db.sh` y
  `scripts/db/supabase_minimo.sql` (D-16).
- **Aceptación:**
  - ✔ `anon` no tiene permisos ni políticas; un usuario autenticado sin marco
    no ve nada.
  - ✔ Admin de A no ve ni cambia nada de B; dispositivo A no ve B, no borra ni
    edita familiares, solo marca "me gusta" y crea alertas de su marco.
  - ✔ Bucket `photos` privado: cada uno ve solo `<su frame_id>/…`.
  - ✔ Integridad: remitente y confirmaciones del mismo marco, ruta de la foto
    con el id de su marco, hash y formato válidos, una foto por hash y marco.
  - ✔ 103 pruebas pgTAP en PostgreSQL 16 con la imitación mínima de Supabase;
    tres errores introducidos a propósito en la migración se detectan.
  - ✔ Las mismas pruebas con la CLI oficial (`supabase test db`) en GitHub
    Actions (commit `5e570e7`).
- **No incluido (decisión del equipo):** crear el proyecto remoto, región y
  plazos de conservación (D-12), alta de marcos y administradores desde el
  panel (por ahora solo con `service_role`), resolver alertas desde el marco
  (D-08).
- **HW:** ninguno. **Requiere autorización** para crear el proyecto
  remoto y aplicar migraciones (no se hará sin permiso explícito).

## 5. Telegram y autorización de familiares — *completada en local; sin bot real*
- **Objetivos:** recibir fotos solo de familiares registrados; vinculación
  segura (código de un solo uso generado desde el panel); respuestas claras
  al remitente; nada de Messenger.
- **Decisión (D-05):** webhook en una Edge Function de Supabase.
- **Archivos:** `supabase/migrations/20261102120000_vinculacion_telegram.sql`
  (códigos), `supabase/functions/telegram-webhook/` (`handler.ts` lógica,
  `images.ts` metadatos, `telegram.ts` descargas, `store.ts` Supabase,
  `index.ts` arranque), `scripts/test_functions_e2e.sh`.
- **Incluye (movido desde la fase 2):** quitar metadatos (EXIF con GPS, XMP,
  IPTC, comentarios) al recibir, conservando solo la orientación (D-18). La
  reducción de resolución pasa a la fase 6, en la Pi (D-18).
- **Aceptación:**
  - ✔ Remitente no registrado o desactivado → "Este bot es privado y usted
    no está en la lista blanca."; su foto ni se descarga.
  - ✔ Foto válida → archivo en el bucket + fila `photos`; repetida → aviso
    de duplicada; familiar de dos marcos → llega a ambos.
  - ✔ No imagen, formato no admitido, dañada o > 10 MB (declarado o real) →
    rechazada con un mensaje claro.
  - ✔ Webhook sin `secret_token` correcto → 401; sin secreto configurado →
    nunca acepta mensajes.
  - ✔ Código caducado, reutilizado, anulado o de un familiar desactivado →
    rechazado (pgTAP).
  - ✔ Metadatos quitados en JPEG, PNG y WebP reales generados con Pillow:
    sin GPS, misma imagen y misma orientación.
  - ✘ Pendiente de GitHub Actions: `store.ts` contra Supabase local y la
    función servida por el runtime oficial (`test_functions_e2e.sh`).
  - ✘ Sin bot real ni proyecto remoto (requieren autorización).
- **No incluido:** límite de mensajes por persona, vídeos, fotos en grupos.
- **HW:** ninguno. **Requiere** crear un bot de pruebas (lo hace el equipo;
  el token nunca se sube al repositorio).

## 6. Sincronización y confirmaciones
- **Objetivos:** `sync` descarga fotos nuevas y rellena `remote_id`
  (`LocalStore.mark_synced`), sin volver a descargar las retiradas
  (`evicted_at`); `dispatcher` vacía el outbox (SOS, confirmaciones,
  "me gusta", `photo_deleted`) con reintentos e idempotencia; recibir
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
