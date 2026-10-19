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
| D-05 | Recepción de Telegram mediante webhook en Supabase Edge Function | Pendiente ⚠ |
| D-06 | El marco usa un usuario Supabase propio, nunca `service_role` | Adoptada ⚠ |
| D-07 | Fotografías remotas en bucket privado de Supabase Storage | Provisional ⚠ |
| D-08 | La alarma local sigue sonando tras la confirmación de un familiar | Pendiente |
| D-09 | Galería con pygame-ce (ventana) + Pillow (imagen), extra `[display]` | Adoptada ⚠ |
| D-10 | `gpiozero` para los botones | Provisional |
| D-11 | Alojamiento del panel web | Pendiente ⚠ |
| D-12 | Retención y borrado de fotografías y datos personales | Pendiente ⚠ |

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
**Decisión necesaria antes de la fase 5.**

## D-06 Credenciales de Supabase en el marco ⚠
La clave `service_role` se salta RLS: si alguien roba el marco tendría acceso
a toda la base de datos. Por eso el marco inicia sesión como un usuario Auth
propio (`SUPABASE_DEVICE_EMAIL`/`PASSWORD`) y RLS lo limita a su `frame_id`.
`service_role` solo existirá en funciones del servidor.

## D-07 Storage ⚠
Bucket privado; acceso mediante URLs firmadas de corta duración o descarga
autenticada del usuario del marco. Verificar el almacenamiento incluido en el
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
