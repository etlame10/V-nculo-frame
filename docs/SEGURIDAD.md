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
- La galería solo abre archivos dentro de la carpeta de fotos: rechaza
  nombres con separadores, `..` o caracteres nulos (`gallery/imaging.py`).
- Borrar o retirar una foto solo actúa sobre nombres con el formato que crea
  el propio marco (`<sha256>.jpg|png|webp`); cualquier otro nombre en la base
  de datos se rechaza sin tocar el disco (`library.py`).
- Borrar una foto elimina fila y archivo en la misma transacción y, si había
  copia remota, encola su borrado allí. Las copias `*.bak` de la base de datos
  y `data/quarantine/` pueden conservar metadatos o fotos borradas: entran en
  la política de retención pendiente (D-12).
- Al recibir una foto, la Edge Function quita los metadatos (EXIF con GPS,
  XMP, IPTC, comentarios) antes de guardarla y conserva solo la orientación
  (D-18). Las fotos que ya estuvieran en el marco antes no se reescriben.

## Validación de entradas externas

- Fotografías: tamaño máximo configurable y firma real de bytes (JPEG, PNG,
  WebP); se rechaza el resto (`media.py`). Al mostrarlas, la galería vuelve
  a validar con Pillow: solo esos formatos y un máximo de 40 megapíxeles
  ("bombas de descompresión"); cualquier fallo se muestra como aviso.
- Telegram (fase 5, `supabase/functions/telegram-webhook/`):
  - webhook verificado con `secret_token` en tiempo constante; sin él → 401,
    y si el secreto no está configurado no se acepta nada;
  - solo chats privados; grupos, canales, bots y mensajes editados se ignoran;
  - solo `telegram_user_id` vinculados con un código de un solo uso (D-19) y
    activos; al resto: "Este bot es privado y usted no está en la lista
    blanca." y su foto ni se descarga;
  - descarga limitada a 10 MB aunque Telegram declare otro tamaño; firma real
    de bytes (JPEG, PNG, WebP); archivos dañados rechazados;
  - el token del bot solo vive en los secretos de la función; los errores no
    incluyen la URL de descarga (que lo contiene);
  - los textos se tratan como datos, nunca como comandos privilegiados.
- Configuración: rangos validados; `SUPABASE_URL` debe ser `https://`.

## Superficie expuesta

- La Raspberry Pi no abre puertos ni expone HTTP. GPIO y alarma solo se
  controlan desde procesos locales.
- Acciones remotas sobre el marco (p. ej. resolver un SOS) se hacen escribiendo
  en Supabase con un usuario autorizado; el marco las lee y valida contra su
  estado (`SosMachine` rechaza alertas desconocidas).
- El panel web exige inicio de sesión (Supabase Auth) y solo ve los marcos de
  `frame_admins`.

## RLS y permisos (fase 4, probado en local)

Migración `supabase/migrations/20261102090000_esquema_inicial.sql`. RLS
activado en **todas** las tablas; `anon` no tiene permisos ni políticas.
Además de RLS (qué filas), los permisos por columna limitan qué campos puede
escribir `authenticated` (D-17).

| Tabla | Administrador del marco | Usuario dispositivo del marco |
|---|---|---|
| `frames` | leer los suyos | leer el suyo |
| `frame_admins` | leer las filas de sus marcos | — |
| `family_members` | leer; crear (`frame_id`, `display_name`); editar `display_name` y `active` | leer los de su marco |
| `photos` | leer y borrar en sus marcos | leer; actualizar solo `liked_at` |
| `sos_alerts` | leer; resolver una vez, firmando con su propio usuario | crear (`id`, `frame_id`, `triggered_at`) y leer |
| `sos_acks` | leer | leer |
| Storage `photos/<frame_id>/…` | leer y borrar en sus marcos | leer en su marco |

Nadie con sesión normal puede: crear marcos o administradores, escribir
`telegram_user_id`, borrar familiares (se desactivan), insertar fotos,
crear confirmaciones SOS ni mover filas de un marco a otro. Eso lo harán
funciones del servidor con `service_role` (bot, vinculación, alta de marcos).

Notas:
- Ayudantes `private.is_frame_admin`, `private.is_frame_device`
  (`SECURITY DEFINER`, `search_path` vacío) y `private.frame_id_from_path`,
  que devuelve `NULL` ante una ruta mal formada. El esquema `private` no se
  expone en la API y `anon` no puede usarlo.
- Integridad en la propia base de datos: el remitente de una foto y quien
  confirma una alerta deben ser familiares **del mismo marco** (claves
  foráneas compuestas); la ruta de la foto empieza por su `frame_id`.
- El bucket `photos` es privado, admite solo JPEG, PNG y WebP y hasta 10 MB.
- Probado con 103 pruebas pgTAP (`supabase/tests/database/`). **No** se ha
  aplicado en ningún proyecto remoto.

## Hardware

Los GPIO de la Raspberry Pi funcionan a **3,3 V y no toleran 5 V**. No se
propondrán conexiones definitivas hasta verificar los componentes reales
(ver INVENTARIO_HARDWARE.md).

## Alcance del SOS

Función complementaria, no certificada. La documentación de usuario deberá
indicarlo y recomendar mantener los medios de emergencia habituales (112).
