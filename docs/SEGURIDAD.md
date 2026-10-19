# Seguridad

## Secretos

- Los secretos solo existen en `.env` del dispositivo o en los secretos de
  Supabase/GitHub. `.env` está en `.gitignore`; `.env.example` solo contiene
  valores ficticios.
- `Settings` oculta el token de Telegram y la contraseña del dispositivo en
  su `repr`, y `python -m vinculo_frame check` solo dice si están
  configurados (probado en `tests/test_config.py` y `tests/test_cli.py`).
- La clave `service_role` de Supabase **nunca** se instala en la Pi ni llega
  al navegador (D-06). Solo la usarán funciones del servidor.
- Si un token se filtra: revocarlo (BotFather `/revoke`, rotar claves en
  Supabase) y limpiar el historial; borrar el archivo no basta.
- Recomendado: activar *secret scanning* y *push protection* en GitHub
  (ajuste del repositorio; no se ha cambiado desde esta sesión).

## Datos privados

- `data/`, bases SQLite y todos los formatos de imagen están ignorados por
  git. Las pruebas generan bytes sintéticos, nunca fotos reales.
- Las fotos se guardan con nombre = SHA-256 del contenido, sin usar datos
  del remitente en rutas.
- Pendiente (fase 2): eliminar metadatos EXIF (puede incluir ubicación GPS)
  al recibir.

## Validación de entradas externas

- Fotografías: tamaño máximo configurable y firma real de bytes (JPEG, PNG,
  WebP); se rechaza el resto (`media.py`). En la fase 2 se añadirá
  decodificación completa con límite de píxeles para evitar "bombas de
  descompresión".
- Telegram (fase 5): solo se aceptan mensajes de `telegram_user_id`
  registrados y activos; webhook verificado con `secret_token`; los textos
  se tratan como datos, nunca como comandos privilegiados.
- Configuración: rangos validados; `SUPABASE_URL` debe ser `https://`.

## Superficie expuesta

- La Raspberry Pi no abre puertos ni expone HTTP. GPIO y alarma solo se
  controlan desde procesos locales.
- Acciones remotas sobre el marco (p. ej. resolver un SOS) se hacen escribiendo
  en Supabase con un usuario autorizado; el marco las lee y valida contra su
  estado (`SosMachine` rechaza alertas desconocidas).
- El panel web exige inicio de sesión (Supabase Auth) y solo ve los marcos de
  `frame_admins`.

## Diseño de RLS (borrador para la fase 4)

RLS activado en **todas** las tablas, sin políticas para `anon`.

| Tabla | Administrador del marco | Usuario dispositivo del marco |
|---|---|---|
| `frames` | leer los suyos | leer el suyo |
| `frame_admins` | leer las filas de sus marcos | — |
| `family_members` | leer/crear/editar/desactivar en sus marcos | leer los de su marco |
| `photos` | leer/borrar en sus marcos | leer y actualizar `liked_at` en su marco |
| `sos_alerts` | leer, marcar resuelta | crear y leer en su marco |
| `sos_acks` | leer | leer |
| Storage `photos/<frame_id>/…` | leer/borrar en sus marcos | leer en su marco |

Notas:
- Escrituras del bot (fotos entrantes, `sos_acks` desde Telegram) las hace la
  Edge Function con `service_role`, tras validar al remitente.
- Ayudante previsto: función `is_frame_admin(frame_id)` `SECURITY DEFINER`
  con `search_path` fijo, para no repetir subconsultas en cada política.
- Las políticas se probarán con usuarios de prueba (admin de A no ve el
  marco B; el dispositivo A no ve el marco B; `anon` no ve nada) antes de
  aplicar cualquier migración remota.

## Hardware

Los GPIO de la Raspberry Pi funcionan a **3,3 V y no toleran 5 V**. No se
propondrán conexiones definitivas hasta verificar los componentes reales
(ver INVENTARIO_HARDWARE.md).

## Alcance del SOS

Función complementaria, no certificada. La documentación de usuario deberá
indicarlo y recomendar mantener los medios de emergencia habituales (112).
