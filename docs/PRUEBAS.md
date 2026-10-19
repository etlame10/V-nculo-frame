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

## Cobertura actual (fases 1 y 2)

Ninguna prueba necesita red, Telegram, Supabase, hardware ni pantalla.

| Archivo | Qué comprueba |
|---|---|
| `test_sos.py` | Pulsación corta sin efecto; activación por `tick` o por `release` tardío; rebotes y pulsaciones repetidas no crean alertas ni reinician el temporizador; confirmaciones duplicadas, tardías o de alertas desconocidas; resolución idempotente; nueva alerta con nuevo id; reloj que retrocede |
| `test_sos_service.py` | Flujo completo sin Internet: alarma local inmediata, avisos que quedan en cola, registro de confirmaciones y resolución |
| `test_storage.py` | Fotos idempotentes por hash, orden, "me gusta" una sola vez; outbox con reintentos y espera exponencial; persistencia al reabrir; rechazo de esquema más nuevo y de fechas sin zona horaria |
| `test_media.py` | Formatos admitidos y rechazados, tamaño máximo, guardado atómico e idempotente, sin restos tras rechazo |
| `test_config.py` | Valores por defecto sin nube, validación de rangos y URL, secretos ocultos en `repr` |
| `test_gallery_playlist.py` | Galería vacía, orden más reciente primero y vuelta, desempate por id, foto única, fotos nuevas prioritarias, foto actual o pendiente borrada, fotos que fallan y reintento |
| `test_gallery_controller.py` | Bienvenida, cambio por intervalo, primera foto al refrescar, foto nueva inmediata, foto única sin recargar, error de lectura → aviso y continúa, todas rotas, error de base de datos, salto manual |
| `test_gallery_text_layout.py` | Fechas en español (Hoy, Ayer, año, reloj adelantado), zona horaria local, nombres limpios y acortados, encaje de imágenes, tamaños de letra por resolución |
| `test_gallery_imaging.py` | JPEG/PNG/WebP, reducción, orientación EXIF, PNG transparente, archivos vacíos/dañados/truncados/inexistentes, límite de píxeles, nombres que intentan salir de la carpeta |
| `test_gallery_render.py` | Foto centrada en cuatro resoluciones y orientaciones, laterales desenfocados, texto del pie, pantallas de bienvenida y error, nombre muy largo |
| `test_gallery_display.py` | Ventana con SDL sin pantalla: bienvenida, fallo de dibujo sin cerrarse, tamaño real, tecla Esc |
| `test_gallery_app.py` | Fotos ficticias a través de `media` y `LocalStore`, idempotencia, vista previa, comandos `demo-photos`, `preview` y `gallery` |
| `test_cli.py` | `check` crea el almacenamiento, no muestra secretos y devuelve error con configuración inválida |

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
