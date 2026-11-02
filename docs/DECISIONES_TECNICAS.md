# Decisiones técnicas

Registro breve de decisiones. Estado: **Adoptada**, **Provisional** (hipótesis
de trabajo, se puede cambiar sin coste) o **Pendiente** (requiere decisión del
equipo). Las marcadas con ⚠ afectan a seguridad, coste o compatibilidad.

| ID | Decisión | Estado |
|---|---|---|
| D-01 | Python ≥ 3.11, solo biblioteca estándar en el núcleo | Adoptada ⚠ |
| D-02 | SQLite local como fuente de verdad del marco | Adoptada |
| D-03 | Patrón outbox para todos los avisos salientes | Adoptada |
| D-04 | Máquina SOS pura con reloj monotónico inyectado | Adoptada |
| D-05 | Recepción de Telegram mediante webhook en Supabase Edge Function | Adoptada ⚠ |
| D-06 | El marco usa un usuario Supabase propio, nunca `service_role` | Adoptada ⚠ |
| D-07 | Fotografías remotas en bucket privado de Supabase Storage | Provisional ⚠ |
| D-08 | La alarma local sigue sonando tras la confirmación de un familiar | Pendiente |
| D-09 | Galería con pygame-ce (ventana) + Pillow (imagen), extra `[display]` | Adoptada ⚠ |
| D-10 | `gpiozero` para los botones | Provisional |
| D-11 | Alojamiento del panel web | Pendiente ⚠ |
| D-12 | Retención y borrado de fotografías y datos personales | Pendiente ⚠ (parte técnica en D-14) |
| D-13 | Migraciones numeradas, transaccionales y con copia previa | Adoptada ⚠ |
| D-14 | Política de conservación: solo se retiran fotos recuperables | Adoptada ⚠ |
| D-15 | Estado de sincronización con dos columnas (`remote_id`, `evicted_at`) | Adoptada |
| D-16 | Pruebas de la base de datos remota: pgTAP con la CLI oficial y con una imitación mínima | Adoptada |
| D-17 | Permisos por columna además de RLS; altas sensibles solo con `service_role` | Adoptada ⚠ |
| D-18 | Metadatos fuera en la nube; reducción de resolución en la Pi | Adoptada ⚠ |
| D-19 | Vinculación de Telegram con códigos de un solo uso | Adoptada ⚠ |

## D-01 Python ≥ 3.11, núcleo sin dependencias
Raspberry Pi OS Bookworm trae Python 3.11 y Trixie 3.13; CI prueba ambas.
El núcleo (SOS, almacenamiento, validación) usa solo la biblioteca estándar,
lo que simplifica la instalación en la Pi. Las librerías de pantalla, GPIO y
red se añadirán como extras opcionales cuando se necesiten.

## D-02 SQLite local
Sin servidor, transaccional, incluido en Python y robusto ante cortes de luz
con WAL. La galería y el SOS leen solo de aquí. El esquema se versiona con
`PRAGMA user_version`.

## D-03 Outbox
Cada aviso (SOS, confirmación, "me gusta") se escribe primero en la tabla
`outbox` local y después lo envía un proceso aparte. Si no hay red, queda
pendiente y se reintenta con espera exponencial (5 s a 5 min). Los avisos SOS
no se descartan nunca. Requiere que el envío sea idempotente (por ejemplo,
incluir `alert_id`) porque un envío puede repetirse si se corta justo después.

## D-04 SOS puro
`SosMachine` no conoce GPIO, Telegram ni la hora del sistema; recibe eventos
con un tiempo monotónico y devuelve efectos. Permite probar todos los casos
(rebotes, pulsaciones repetidas, confirmaciones duplicadas o tardías) sin
hardware. Un cambio de hora del sistema (NTP al recuperar red) no afecta a la
duración de la pulsación.

## D-05 Telegram: webhook en la nube vs. polling en la Pi ⚠
- **Webhook en Supabase Edge Function (recomendada):** recibe fotos aunque la
  Pi esté apagada o sin red; la Pi no expone nada; la validación de
  remitentes ocurre antes de guardar. Telegram permite verificar el webhook
  con `secret_token`. Coste: invocaciones de Edge Functions (verificar el
  límite del plan gratuito vigente).
- **Polling (`getUpdates`) desde la Pi:** más simple, sin código en la nube,
  pero si la Pi está desconectada más tiempo del que Telegram conserva los
  mensajes pendientes, se pierden fotos.

En ambos casos la Pi puede enviar avisos directamente con `sendMessage`
(el webhook no lo impide), lo que da al SOS un camino con menos saltos.

**Adoptada (02/11/2026, decisión del equipo): webhook.** Implementación:
`supabase/functions/telegram-webhook/` con `verify_jwt = false` (Telegram no
envía un JWT) y comprobación del `secret_token` en tiempo constante. Las
respuestas al remitente van en el cuerpo de la respuesta HTTP, sin llamadas
extra a la API. Ante un error de red o de Supabase responde 500 para que
Telegram reintente; las fotos repetidas no se duplican (hash por marco).

## D-06 Credenciales de Supabase en el marco ⚠
La clave `service_role` se salta RLS: si alguien roba el marco tendría acceso
a toda la base de datos. Por eso el marco inicia sesión como un usuario Auth
propio (`SUPABASE_DEVICE_EMAIL`/`PASSWORD`) y RLS lo limita a su `frame_id`.
`service_role` solo existirá en funciones del servidor.

## D-07 Storage ⚠
Bucket privado; acceso mediante URLs firmadas de corta duración o descarga
autenticada del usuario del marco. Creado en la migración de la fase 4 (solo
JPEG, PNG y WebP, máximo 10 MB) y probado en local. Verificar el almacenamiento incluido en el
plan gratuito; si se queda corto, reducir resolución al recibir (fase 5).

## D-08 Alarma tras la confirmación
Hipótesis actual: la alarma sigue hasta que la alerta se resuelve, porque una
confirmación remota no significa que alguien esté presente. En pantalla se
mostrará quién ha confirmado. Se puede cambiar a "silenciar al confirmar"
modificando un solo efecto en `SosMachine.acknowledge`. **Decisión de producto
pendiente**, idealmente con la opinión de usuarios reales.

También falta decidir cómo se resuelve localmente (¿la propia persona puede
cancelar?, ¿un familiar presente?).

## D-09 Pantalla: pygame-ce + Pillow ⚠
Adoptada en la fase 2 tras comprobar en el entorno de desarrollo que ambas
funcionan (SDL sin pantalla y Xvfb a pantalla completa).
- **pygame-ce** (SDL2) abre una ventana a pantalla completa sin necesidad de
  navegador; funciona con Wayland/X11 y, sin escritorio, con KMS/DRM. Consume
  poca memoria y CPU, adecuado para una Pi 4.
- **Pillow** decodifica (con reducción rápida para JPEG), aplica la
  orientación EXIF, limita los píxeles y compone cada diapositiva. Al dibujar
  en una imagen, las pruebas no necesitan pantalla.
- Descartadas: Chromium en modo quiosco (más memoria y un servidor local
  añadido) y Tkinter (no instalado en este entorno; peor control de pantalla
  completa).
- Compatibilidad: Pillow ≥ 10.1, por eso en la Pi se instala con `pip` en un
  entorno virtual (el paquete `apt` de Bookworm es más antiguo). `pygame-ce`
  y `pygame` no deben instalarse a la vez. **No verificado aún en una Pi.**
- El núcleo sigue sin dependencias (D-01): ambas van en el extra `[display]`.

## D-10 GPIO
`gpiozero` es la librería recomendada por Raspberry Pi y funciona en Pi 4 y
Pi 5. Su `MockFactory` permite probar sin hardware. Conexión eléctrica
pendiente del inventario (ver INVENTARIO_HARDWARE.md).

## D-11 Panel web ⚠
Opciones con coste distinto (alojamiento estático gratuito + Supabase Auth,
o un servidor propio). Requisito fijo: el navegador solo recibe la clave
pública de Supabase y toda la autorización la hace RLS.

## D-12 Datos personales ⚠
Se tratan fotografías y datos de personas identificables, incluida una
persona mayor. Al ser un proyecto en contexto de empresa, conviene revisar las
obligaciones de protección de datos (RGPD): base legal, consentimiento de los
familiares, plazo de conservación y región del proyecto Supabase.

En la fase 3 se implementó la parte técnica (borrado completo de fotos,
límite de espacio y conservación, ver D-14). Siguen pendientes las
decisiones legales: plazos concretos, quién puede pedir un borrado y cómo se
propaga a la nube.

## D-13 Migraciones transaccionales ⚠
- Cada versión del esquema es una lista de sentencias en
  `storage._MIGRATIONS`. Una migración publicada no se modifica: se añade otra.
- Cada paso se ejecuta entre `BEGIN IMMEDIATE` y `COMMIT`, junto con el
  cambio de `user_version`. Si algo falla, se deshace todo y la base de datos
  queda en la versión anterior (probado con un fallo a mitad de un paso).
- Se sustituyó `executescript`, que confirma la transacción en curso antes de
  ejecutarse y por tanto no permitía deshacer una migración a medias.
- Antes de migrar una base de datos existente se guarda
  `vinculo.sqlite3.v<versión>.bak` con la API de copia de SQLite. Si la copia
  no se puede hacer (por ejemplo, disco lleno), no se migra.
- Una base de datos dañada o de una versión más nueva no se toca: se informa
  del error y se detiene el arranque.
- Compatibilidad: probada la migración de una base de datos creada por el
  código real de la fase 1 (commit `877a094`).

## D-14 Política de conservación ⚠
Límite configurable (`VINCULO_STORAGE_LIMIT_MB`, 2048 por defecto) y reserva
fija de 256 MB de disco libre para el sistema. Si una foto nueva no cabe, solo
se retira el **archivo local** de fotos que cumplan las tres condiciones:
1. tienen copia remota (se pueden recuperar);
2. no tienen "me gusta";
3. tienen más de `VINCULO_KEEP_RECENT_DAYS` días (30 por defecto).

Se retiran las más antiguas primero; los metadatos se conservan. Las
condiciones se comprueban dos veces: al planificar y en la propia sentencia
SQL que retira la foto. Si lo retirable no basta, **no se retira nada**, la
foto nueva se rechaza (`StorageFullError`) y una persona debe decidir.

Consecuencia actual: como aún no hay sincronización, ninguna foto tiene copia
remota y **nunca se retira nada automáticamente**; al llenarse el límite, las
fotos nuevas se rechazan. Con el límite por defecto caben unas 680 fotos de
3 MB. Valores a confirmar cuando se conozca la tarjeta SD (inventario).

`storage --repair` es manual y conservador: los archivos sin fila van a
`data/quarantine/` (no se borran ni se sobrescriben), cada acción se vuelve a
comprobar antes de hacerla, y se niega a actuar si parece una tarjeta o
carpeta desmontada (faltan los archivos de todas las fotos, aunque sea una).

## D-15 Estado de sincronización
Dos columnas nuevas en `photos`, en lugar de tablas de sincronización:
- `remote_id` (único, `NULL` = solo existe en el marco). Sirve a la vez de
  estado y de enlace con la fila remota de Supabase (fase 6).
- `evicted_at`: el archivo local se retiró por espacio o se perdió. La fila se
  conserva para que la sincronización no lo vuelva a descargar en bucle y para
  no perder estadísticas ni "me gusta". La galería no muestra estas fotos.

Lo que sale del marco hacia la nube (borrados, "me gusta", SOS) sigue el
outbox (D-03): borrar una foto con copia remota encola `photo_deleted` en la
misma transacción. Descartado por ahora: marcas de tiempo de modificación o
tablas de cambios, que solo harían falta con edición desde varios sitios.

## D-16 Pruebas de la base de datos remota
- Las migraciones de `supabase/migrations/` se prueban con pgTAP
  (`supabase/tests/database/`), nunca contra un proyecto real.
- **Referencia:** `supabase db start` + `supabase test db` con la CLI oficial
  (job `supabase` de GitHub Actions, Docker).
- **Rápida y sin Docker:** `scripts/test_db.sh` crea un PostgreSQL temporal,
  carga `scripts/db/supabase_minimo.sql` (roles, `auth.uid()`, tablas de
  Storage) y ejecuta las mismas pruebas (job `db`). Se creó porque desde la
  sesión en la nube no se pueden descargar las imágenes de Supabase.
- Riesgo: la imitación puede diferir de Supabase real; por eso el job
  `supabase` es el que decide. Las pruebas de borrado en Storage comprueban
  la condición de la política y no un `DELETE` directo, que Supabase puede
  bloquear fuera de su API.

## D-17 Permisos por columna y altas con `service_role` ⚠
- Además de RLS (qué filas), se retiran los permisos por defecto de Supabase y
  se conceden solo las columnas necesarias: el marco solo cambia
  `photos.liked_at`; el administrador crea familiares con `frame_id` y
  `display_name` y edita `display_name` y `active`; las alertas se crean sin
  resolver y no se borran.
- Crear marcos y administradores, escribir `telegram_user_id`, insertar fotos
  y confirmaciones SOS queda para funciones del servidor con `service_role`
  (fases 5 y 8). Así un fallo en una política no basta para, por ejemplo,
  vincular un Telegram ajeno.
- Los familiares no se borran desde el panel: se desactivan. El borrado real
  (por ejemplo, por una petición RGPD) queda pendiente de D-12.
- El marco **no** puede resolver alertas hasta decidir D-08.

## D-18 Metadatos y resolución de las fotos ⚠
- La Edge Function quita los metadatos **antes de guardar** la foto en la
  nube: EXIF (ubicación GPS, cámara, fechas), XMP, IPTC y comentarios en
  JPEG; `eXIf` y textos en PNG; `EXIF` y `XMP` en WebP. No decodifica la
  imagen: copia solo los bloques necesarios (`images.ts`), así que no pierde
  calidad y no necesita librerías de imagen en Deno.
- Se conserva **solo la orientación**, en un EXIF mínimo nuevo, porque la
  galería la usa para girar la foto. Se conservan el perfil de color ICC y el
  bloque Adobe de JPEG (necesarios para mostrar bien los colores).
- Comprobado con JPEG, PNG y WebP generados con Pillow (no fotos reales): sin
  GPS, misma imagen píxel a píxel tras orientar y misma orientación.
- Las fotos enviadas como "foto" en Telegram ya llegan recomprimidas y sin
  EXIF; las enviadas como "archivo" llegan originales, por eso esta limpieza.
- **Reducir resolución** se hará en la Pi al descargar (fase 6, con Pillow,
  que ya está en el extra `[display]`): en la nube haría falta decodificar
  imágenes dentro de la Edge Function, más lento y frágil. Consecuencia: en
  el bucket se guardan fotos de hasta 10 MB (límite del plan gratuito: 1 GB).

## D-19 Vinculación de Telegram ⚠
- El administrador pide un código para un familiar (`create_link_code`); se
  muestra una vez. Formato `XXXX-XXXX` con 31 símbolos sin confusiones
  (sin 0/O, 1/I/L): unos 40 bits. Caduca a las 24 horas, sirve una vez y
  pedir otro anula el anterior.
- Solo se guarda su SHA-256 (`member_link_codes`, sin permisos ni políticas
  para nadie con sesión). Lo canjea la Edge Function con `service_role`
  (`redeem_link_code`), en una transacción con bloqueo de fila.
- Una cuenta de Telegram es un solo familiar por marco: al vincularla a otro
  familiar del mismo marco, se desvincula del anterior. Puede estar en varios
  marcos (por ejemplo, abuela y abuelo); sus fotos llegan a todos.
- Quien escribe sin estar vinculado recibe "Este bot es privado y usted no
  está en la lista blanca." (decisión del equipo); quien envía un código no
  válido, que no es válido o ha caducado. Ninguna respuesta revela datos.
- Pendiente: limitar intentos por persona si se observa abuso (hoy cada
  intento es un mensaje a Telegram y una consulta).
