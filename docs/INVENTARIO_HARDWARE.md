# Inventario de hardware

**Estado: pendiente.** Solo está confirmado el modelo de placa. El resto de
filas deben rellenarse con lo que haya físicamente disponible (marca, modelo
exacto y, si es posible, enlace a la hoja de datos). No se han supuesto
componentes.

| Componente | Previsto | Modelo real | Datos a verificar | Estado |
|---|---|---|---|---|
| Placa | Raspberry Pi 4 Model B | — (RAM: ?) | Memoria RAM | Confirmado modelo |
| Alimentación de la Pi | Fuente USB‑C | ? | Tensión y corriente nominales; si es la oficial | Pendiente |
| Almacenamiento | Tarjeta microSD | ? | Capacidad, clase A1/A2 | Pendiente |
| Pantalla | HDMI integrada en carcasa | ? | Resolución, tamaño, conector (micro‑HDMI en la Pi 4), alimentación, si es táctil | Pendiente |
| Cable de vídeo | micro‑HDMI → ? | ? | Conector del lado de la pantalla | Pendiente |
| Botón "me gusta" | Pulsador | ? | Tipo (momentáneo NA), si lleva LED y a qué tensión | Pendiente |
| Botón SOS | Pulsador independiente | ? | Ídem; tamaño y protección contra pulsación accidental | Pendiente |
| Alarma local | Zumbador o altavoz | ? | Activo/pasivo, tensión, consumo | Pendiente |
| Cableado | Dupont, conectores | ? | — | Pendiente |
| Carcasa | Impresa en 3D | ? | Ventilación, acceso a puertos y microSD | Pendiente |
| Reloj (RTC) | No previsto | — | La Pi 4 no tiene RTC; la hora se toma de NTP | Ver nota |

## Notas para cuando haya inventario

- Los GPIO trabajan a **3,3 V** y **no toleran 5 V**. Ningún componente
  alimentado a 5 V debe conectarse directamente a un GPIO.
- Hipótesis provisional, **no verificada**: un pulsador simple entre un GPIO
  y GND, usando la resistencia *pull‑up* interna, no introduce tensiones
  externas. Se confirmará con el pulsador real antes de cablear.
- Un zumbador que consuma más corriente de la que admite un GPIO necesitará
  una etapa de conmutación (transistor). No se diseña hasta conocer el modelo.
- Sin RTC, tras un corte sin red la hora del sistema puede ser incorrecta.
  Por eso la duración del SOS usa reloj monotónico (D-04); las fechas
  mostradas en la galería deberán tolerarlo (fase 2).
- Verificar disipación térmica dentro de la carcasa con la pantalla encendida
  de forma continua.

## Asignación de pines

Pendiente. Se documentará aquí (número BCM, función, componente) en la fase 7.
