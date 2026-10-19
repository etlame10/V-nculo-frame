# Pruebas

## Cómo ejecutar

```bash
python -m pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest
```

GitHub Actions (`.github/workflows/tests.yml`) ejecuta lo mismo en cada push
y pull request, con Python 3.11 y 3.13.

## Cobertura actual (fase 1)

Ninguna prueba necesita red, Telegram, Supabase ni hardware.

| Archivo | Qué comprueba |
|---|---|
| `test_sos.py` | Pulsación corta sin efecto; activación por `tick` o por `release` tardío; rebotes y pulsaciones repetidas no crean alertas ni reinician el temporizador; confirmaciones duplicadas, tardías o de alertas desconocidas; resolución idempotente; nueva alerta con nuevo id; reloj que retrocede |
| `test_sos_service.py` | Flujo completo sin Internet: alarma local inmediata, avisos que quedan en cola, registro de confirmaciones y resolución |
| `test_storage.py` | Fotos idempotentes por hash, orden, "me gusta" una sola vez; outbox con reintentos y espera exponencial; persistencia al reabrir; rechazo de esquema más nuevo y de fechas sin zona horaria |
| `test_media.py` | Formatos admitidos y rechazados, tamaño máximo, guardado atómico e idempotente, sin restos tras rechazo |
| `test_config.py` | Valores por defecto sin nube, validación de rangos y URL, secretos ocultos en `repr` |
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

## Escenarios de aceptación previstos (fase 9)

- Desconectar la red, pulsar SOS 3 s: suena la alarma al instante; al volver
  la red, el aviso llega a todos los familiares una vez.
- Pulsación corta o rebotes en SOS: no hay alerta.
- Reiniciar la Pi con avisos pendientes: se envían tras el arranque.
- Foto de un remitente no registrado: no aparece en el marco.
- Cortar la luz durante la recepción de una foto: no queda archivo corrupto.
- 24 h de funcionamiento continuo: temperatura y memoria estables.
