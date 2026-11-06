# Diseño de firmware — batonAI (v0.1)

**Estado:** diseño de la Fase C. No hay código de firmware todavía; este documento
fija la arquitectura antes de comprar/encender hardware.
**Hardware objetivo:** ESP32-S3 DevKitC-1 **N16R8** (16 MB flash, 8 MB PSRAM
octal), TFT 3,5" 480×320 SPI (ST7796/ILI9488), INMP441, MAX98357A, encoder
rotativo, 2 Choc (A/B) y PTT.
**Framework:** ESP-IDF v5.x (C), LVGL v9 mediante `esp_lvgl_port`.
**Contrato externo:** protocolo v1 del gateway, definido en
[`DISENO_SOFTWARE_BATONAI.md`](DISENO_SOFTWARE_BATONAI.md).

---

## 1. Qué es y qué no es este firmware

El dispositivo es un **cliente ligero del gateway**, no un asistente de voz
autónomo.

- **Es:** un panel que muestra estado, navega con un encoder y resuelve
  aprobaciones con A/B y PTT.
- **No es:** un cliente de APIs de LLM, ni un reproductor de TTS, ni un
  orquestador. No guarda API keys, no llama a Anthropic/OpenAI y no decide si
  una aprobación es válida.
- **La voz termina en una transcripción con preview**, que el usuario confirma
  antes de que el gateway la inyecte al agente. No hay «pregunta al LLM y
  respuesta hablada».

Consecuencias directas:

1. El único destino de red es el gateway (`wss://`), en la LAN.
2. El pipeline de audio es `PTT → PCM → gateway → transcript → preview → A`.
3. El altavoz existe para **tonos y avisos**, no para TTS en v1.
4. Si el gateway cae, el dispositivo muestra `OFFLINE`; el trabajo sigue en el
   PC con los prompts nativos.

---

## 2. Capas

```text
┌────────────────────────────────────────────────────────────┐
│ app/            pantallas, máquina de estados, acciones    │
│   screens/      ambient, dashboard, detail, modal, dictation│
│   ui_model      copia inmutable del estado para renderizar │
├────────────────────────────────────────────────────────────┤
│ domain/         protocolo y reglas del dispositivo         │
│   protocol      parseo/serialización JSON, validación      │
│   state_cache   agentes, cola de aprobaciones, reloj       │
│   session       handshake, seq, reconexión, pendientes     │
│   ptt           máquina de estados del dictado             │
├────────────────────────────────────────────────────────────┤
│ services/       tareas FreeRTOS y periféricos              │
│   net_control   WSS JSON                                   │
│   net_audio     WSS binario PCM                            │
│   audio_in      I2S RX + anillo + streaming                │
│   audio_out     I2S TX para tonos                          │
│   input         encoder PCNT + A/B/PTT                     │
│   storage       NVS, configuración, token                  │
│   provisioning  SoftAP + portal cautivo                    │
│   ota           descarga, verificación y rollback          │
├────────────────────────────────────────────────────────────┤
│ bsp/            pines, display, I2S, alimentación          │
└────────────────────────────────────────────────────────────┘
```

Regla de dependencias: `app` no toca drivers; `services` no toca LVGL; `domain`
no conoce FreeRTOS salvo por colas abstractas. Así la lógica de protocolo y la
máquina de estados se pueden probar en el host.

---

## 3. Modelo de ejecución (FreeRTOS)

Dos núcleos, tareas con prioridad fija y un único dueño de LVGL.

| Tarea | Core | Prio | Stack | Responsabilidad |
|---|---:|---:|---:|---|
| `ui_task` | 1 | 6 | 8 KB | `lv_timer_handler()` cada 5 ms; aplica eventos de la cola; único que llama a LVGL |
| `input_task` | 1 | 7 | 4 KB | Encoder (PCNT), debounce de A/B/PTT, cola de eventos |
| `net_control` | 0 | 5 | 8 KB | WSS JSON, handshake, ping/pong, reconexión |
| `net_audio` | 0 | 5 | 6 KB | WSS binario, envío de frames PCM |
| `audio_in` | 0 | 6 | 4 KB | I2S RX → anillo → frames de 20 ms |
| `audio_out` | 0 | 4 | 3 KB | Tonos por I2S TX, mute del amplificador |
| `housekeeping` | 0 | 2 | 4 KB | Brillo, watchdog, estadísticas, OTA |

Criterios:

- **Nadie más que `ui_task` llama a LVGL.** La red y el input publican eventos
  en `app_queue`; la UI los consume y renderiza.
- Las ISR solo hacen `xQueueSendFromISR`/contadores: nada de `malloc`, nada de
  LVGL, nada de logs.
- `ui_task` y `net_control` se suscriben al *task watchdog*; si la UI se bloquea
  más de 5 s, el dispositivo se reinicia.
- Prioridades: el input manda sobre la UI (un botón debe responder siempre);
  el audio de entrada manda sobre el de salida; la red no debe bloquear al
  audio (DMA + colas cortas).
- El stack de WiFi/LWIP lo gestiona ESP-IDF en sus propias tareas; el reparto
  «Core 0 red/audio, Core 1 UI/input» es una guía, no una jaula.

### 3.1. Comunicación entre tareas

| Cola | Productor | Consumidor | Tamaño |
|---|---|---|---:|
| `app_queue` | input, net, ptt | UI | 16 eventos |
| `audio_frame_q` | audio_in | net_audio | 8 frames (20 ms) |
| `tone_q` | UI/app | audio_out | 4 tonos |
| `state_lock` | net_control | UI (copia) | mutex |

El estado compartido es una estructura pequeña (`agents[3]`, cola de
aprobaciones, `system`, `clock`). La UI toma el mutex, copia y suelta antes de
renderizar: nunca se pinta con el mutex tomado.

---

## 4. Arranque

```text
app_main
 ├─ NVS + configuración (WiFi, token, brillo, idioma)
 ├─ BSP: display (backlight apagado), I2S, encoder, botones
 ├─ LVGL: display, buffers, indevs, fuentes, pantalla BOOT
 ├─ ¿WiFi configurado? ──no──► PROVISIONING (SoftAP + portal)
 │        sí
 ├─ arranca net_control/net_audio, audio_in/out, input, housekeeping
 ├─ UI: CONNECTING → handshake → state
 └─ WDT on; backlight on
```

El display se enciende al final para no mostrar basura. El amplificador arranca
con `SD/EN` a nivel bajo (mute) y se habilita tras configurar I2S TX.

---

## 5. Mapa de pines y BOM

### 5.1. Pinout propuesto (validar con la placa concreta)

| Función | GPIO | Periférico | Notas |
|---|---:|---|---|
| LCD SCLK | 12 | SPI2 | |
| LCD MOSI | 11 | SPI2 | |
| LCD CS | 10 | | |
| LCD DC | 9 | | |
| LCD RST | 8 | | |
| LCD BL | 7 | LEDC PWM | Brillo 5 kHz |
| Mic SCK | 4 | I2S0 | |
| Mic WS | 5 | I2S0 | |
| Mic SD | 6 | I2S0 | L/R a GND → canal izquierdo |
| Amp BCLK | 15 | I2S1 | |
| Amp LRC | 16 | I2S1 | |
| Amp DIN | 17 | I2S1 | |
| Amp SD/EN | 18 | GPIO | Mute al arrancar |
| Encoder A | 38 | PCNT0 | Pull-up interno |
| Encoder B | 39 | PCNT0 | Pull-up interno |
| Encoder push | 40 | GPIO | Opcional; reserva |
| Botón A | 41 | GPIO | Pull-up, flanco + debounce |
| Botón B | 47 | GPIO | Verifica LED RGB de la placa |
| PTT | 21 | GPIO | Pulsador grande |
| LED micrófono | 42 | GPIO | Opcional, activo al grabar |

Advertencias:

- GPIO 26–32 son flash interna y 33–37 PSRAM octal en el N16R8: no se tocan.
- GPIO 19/20 son USB; 0/3/45/46 son *strapping*: evitar.
- 39–42 son JTAG. Se pueden usar como GPIO, pero no depures por JTAG externo
  mientras estén ocupados.
- Algunas DevKitC-1 llevan LED RGB en **GPIO48**: si es tu caso, no uses 48.
- El encoder es un EC11 con 20 muescas por vuelta; se alimenta a 3,3 V y usa
  pull-ups internos (o 10 kΩ externos si el ruido es alto).

### 5.2. Cambios en la lista de compra

El esquema elegido (encoder + A/B + PTT) sustituye el D-pad de 4 pulsadores:

| Antes | Ahora |
|---|---|
| 4 táctiles para D-pad | 1 encoder EC11 con muescas (+ knob) |
| 1 táctil para PTT | 1 táctil para PTT (sin cambio) |
| 2 Choc A/B | 2 Choc A/B (sin cambio) |

Consecuencia mecánica: el encoder va montado en la carcasa con su eje y knob; no
puede compartir hueco con el D-pad. Hay que actualizar `LISTA_COMPRA_BATONAI.md`
y el diseño de la tapa inferior cuando se cierre la mecánica.

---

## 6. Pantalla, LVGL y memoria

### 6.1. Configuración de pantalla

- ST7796S o ILI9488 por SPI2 a **40 MHz** (subir a 80 MHz solo con cable corto
  y buena integridad; a través de la bisagra, no).
- 480×320, RGB565, `esp_lcd_panel_io_spi` + driver ST7796 propio o del
  componente `esp_lcd_st7796` (no todos los drivers vienen en el core de IDF).
- **Dos buffers parciales de 480×40 px** (38,4 KB cada uno, 76,8 KB en total)
  en RAM interna DMA:

```c
static uint8_t *buf1, *buf2;
size_t size = 480 * 40 * sizeof(uint16_t);
buf1 = heap_caps_malloc(size, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
buf2 = heap_caps_malloc(size, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
lv_display_set_buffers(disp, buf1, buf2, size, LV_DISPLAY_RENDER_MODE_PARTIAL);
```

- `lv_display_flush_ready()` se llama en el callback `on_color_trans_done` del
  panel; no se bloquea la UI esperando al SPI.
- **No** se usa un framebuffer completo en PSRAM: 307 KB por buffer, doble
  buffer y DMA desde PSRAM dan peor refresco y más latencia que el refresco
  parcial.
- Objetivo: 20–30 fps en transiciones; el dashboard en reposo no necesita más
  de 5 fps porque solo cambian contadores de tiempo.

### 6.2. Memoria

| Uso | Dónde | Presupuesto |
|---|---|---:|
| Buffers LVGL | RAM interna DMA | 77 KB |
| Heap de LVGL (objetos, estilos) | RAM interna | 48–64 KB |
| Fuentes e iconos | flash (rodata) | 0,4–1 MB |
| Anillo de audio | PSRAM | 480 KB (15 s) |
| Frames DMA I2S | RAM interna | 4 × 1,3 KB |
| Dos sesiones TLS | RAM interna | 50–80 KB |
| Buffers JSON/WSS | RAM interna | 16–24 KB |
| Stacks de tareas | RAM interna | ~37 KB |
| WiFi/LWIP | RAM interna | ~50 KB |

El N16R8 tiene 512 KB de SRAM interna; el presupuesto es viable pero **sin
margen para lujos**. Si faltara RAM, la primera medida es pasar a **un solo
WebSocket** con frames tipados (el gateway ya separa audio y control; el
firmware puede negociar una sola conexión en una revisión futura). La segunda,
reducir el heap de LVGL y liberar pantallas no visibles.

### 6.3. Fuentes y textos

- `lv_font_conv` con subconjunto Latin-1: acentos, `€`, `→`, `✓`, `✗`, `⏸`.
- Estados a 16 px; logs monoespaciados a 13–14 px; títulos a 20 px.
- Una sola familia visual; el dashboard debe leerse a 50–70 cm, no a 30 cm.
- No usar solo color para el estado: icono + palabra + forma.

### 6.4. Navegación con encoder

- `lv_indev` tipo `LV_INDEV_TYPE_ENCODER` para el giro.
- `lv_indev` tipo `LV_INDEV_TYPE_KEYPAD` para A/B, unido al mismo grupo.
- Grupos: uno por pantalla; al cambiar de pantalla se activa su grupo con
  `lv_group_set_default`.
- Giro → `LV_KEY_NEXT`/`LV_KEY_PREV`; A → `LV_KEY_ENTER`; B → `LV_KEY_ESC`.
- **Excepción deliberada:** en el modal de aprobación con riesgo alto, A no se
  entrega a LVGL. La app mide la pulsación, dibuja el anillo y solo entonces
  envía la confirmación. LVGL no decide cuándo una aprobación es válida.
- PTT nunca pasa por LVGL: es un evento `APP_EVT_PTT_DOWN`/`UP` de la app.

---

## 7. Máquina de estados de la interfaz

```text
BOOT → PROVISIONING (si no hay WiFi)
     → CONNECTING → OFFLINE ⇄ AMBIENT/DASHBOARD
DASHBOARD ⇄ DETAIL
DASHBOARD → MODAL (si hay aprobación)
DETAIL    → MODAL
MODAL     → DICTATION (si la opción es responder por voz)
DICTATION → DASHBOARD/DETAIL
```

| Pantalla | Contenido | Encoder | A | B | PTT |
|---|---|---|---|---|---|
| `AMBIENT` | Solo contador y estado global, sin ruido | Despierta a `DASHBOARD` | Abre dashboard | — | — |
| `DASHBOARD` | 2–3 tarjetas, `WAITING_INPUT` primero | Mueve el foco | Abre detalle | — | — |
| `DETAIL` | Conversación: burbujas, tarea y coste | Scroll de mensajes | Envía el preview del dictado | Vuelve; mantener = interrumpir | Graba y genera preview |
| `MODAL` | Hoja inferior: comando, `cwd`, riesgo, caducidad, 2–4 opciones | Selecciona opción | Confirma la opción enfocada (hold si `hold_ms>0`) | Vuelve y cancela | Responde por voz |
| `DICTATION` | Preview de la transcripción | — | Envía | Cancela | Regraba |
| `OFFLINE` | «Gateway desconectado» + antigüedad | — | Reintenta | — | — |
| `PROVISIONING` | SSID del AP y URL del portal | — | — | — | — |

Reglas:

- **Una sola modal a la vez.** Si hay varias, la cola se muestra como `+N en
  cola` y se resuelve en orden de llegada, no por agente.
- `EXPIRED` y `STALE` cierran la modal y muestran un aviso breve; nunca se
  quedan congeladas.
- `OFFLINE` no muestra la última telemetría como si fuera actual: la atenúa y
  muestra la edad del último `state`.
- El modo ambiente apaga la retroiluminación tras 60 s sin eventos y la deja al
  10 %; un `WAITING_INPUT` nuevo la enciende y emite el tono.

### 7.1. Reloj sin RTC

El ESP32 no tiene RTC de pared. Para la cuenta atrás de `expires_at`:

- al recibir `welcome`, se toma `server_time` como ancla;
- cada `state` trae `ts`, que reajusta el ancla;
- `now_servidor = ancla + (esp_timer_get_time() - t_ancla)`.

Así no hace falta SNTP. Si el dispositivo se queda sin conexión, la cuenta atrás
se detiene y la modal se cierra como «caducada» al reconectar.

### 7.2. Composición visual en 480×320

La pantalla usa la misma gramática que el panel web: fondo negro, tarjetas
redondeadas, un icono por agente y un punto de estado **acompañado de palabra**
(no solo color). Lo que cambia es la densidad.

```text
┌────────────────────────────────┬──────────────┐
│ ┌──────────┐ ┌──────────┐      │ Dashboard    │
│ │ ✳ Claude │ │ >_ Codex │      │              │
│ │   ●      │ │   ●      │      │ esperando    │
│ │ Limpiar  │ │ Refact.  │      │ respuesta  1 │
│ └──────────┘ └──────────┘      │ trabajando 1 │
│ ┌──────────┐ ┌──────────┐      │ en espera  1 │
│ │ A Gemini │ │  libre   │      │ error      0 │
│ └──────────┘ └──────────┘      │ ● conectado  │
└────────────────────────────────┴──────────────┘
```

Decisiones de composición:

- **Rejilla de dos columnas + raíl de 128 px**, igual que el panel de referencia:
  352 px para tarjetas y 128 px para los contadores.
- Tarjeta de ~162×104 px, radio 13 px: icono 26 px, nombre 10,5 px, modelo 6,8 px,
  punto de estado 7 px, tarea 8,5 px a dos líneas y último log 6,6 px.
- Se mantienen **seis huecos** (2×3) y la rejilla hace scroll; los huecos libres
  son un borde discontinuo sin texto, como en el tablero de referencia.
- El raíl sustituye a la barra superior: cuatro contadores como tarjetas con
  color (ámbar, verde, azul, rojo), una barra de distribución de la flota,
  coste/tokens y el estado de conexión en una píldora al pie.
- La tarjeta `WAITING_INPUT` va primera, con borde ámbar y el punto pulsando; la
  de error, con borde rojo; el resto, gris.
- El dispositivo recibe todos los agentes y aplica la política `hidden_agents`
  del gateway: los ocultos no se muestran ni alertan, aunque el gateway siga
  conociéndolos y auditándolos.
- Los agentes **fijados** (`pinned_agents`, máximo 2) van arriba del todo, en su
  orden de fijado y con una marca de pin; el resto sigue el orden por estado. Si
  un fijado está oculto, el ojo manda y no se muestra.
- La tarjeta muestra la **última salida** del agente en la tarea: texto del
  asistente o `→ herramienta: comando/ruta`.
- Al pasar un agente visible de `RUNNING`/`WAITING_INPUT` a `DONE`/`IDLE`, el
  firmware reproduce un **ding** de dos tonos (880/1320 Hz, ~0,5 s) por I2S al
  MAX98357A. Los agentes ocultos no suenan.
- La aprobación es una **hoja inferior** (~70 % de alto) que no tapa el
  dashboard: título 13 px, comando mono 9,5 px en una caja con scroll, `cwd`
  7,5 px, opciones con foco del encoder, botones 10 px y anillo de confirmación
  de 2 px. Detrás sigue visible la primera fila de tarjetas.
- La pantalla `DETAIL` es la **conversación** del agente: burbujas de mensajes,
  tarea en la cabecera y compositor con PTT. Mantener PTT graba; al soltar se
  muestra la transcripción simulada y A la envía / B la cancela. El encoder hace
  scroll de los mensajes.
- Iconos de 26 px (bitmap o trazo LVGL), sin logotipos registrados: glifo +
  color del proveedor.
- Sin degradados ni sombras: en un TFT de 3,5" no aportan y cuestan ancho de
  banda. Contraste de texto ≥ 7:1.
- Solo dos animaciones: el pulso del punto en `WAITING_INPUT` (2,4 s) y el anillo
  de confirmación. Todo lo demás es estático.
- En `AMBIENT`, la retroiluminación baja al 10 % y se mantiene solo el contador
  del raíl; un `WAITING_INPUT` nuevo la enciende.

> **Aviso de legibilidad física.** A 160 dpi, 6,8 px son ~1,1 mm: el modelo y el
> log se leen en el monitor a 480 CSS px, pero en la pantalla real hay que
> validarlos a 50–70 cm. Si no se leen, la primera medida es subir nombre/tarea
> y ocultar el modelo; la segunda, reducir a cuatro tarjetas más grandes. La
> composición no cambia, solo la densidad.

---

## 8. Entradas

### 8.1. Encoder

- Decodificación por **PCNT** (no `attachInterrupt`): cuatro flancos por muesca.
- Se acumulan flancos y se emite un paso cada 4 (configurable si el encoder es
  de otra resolución).
- Filtro de glitches de PCNT activado; si aun así se pierden pasos a gran
  velocidad, subir el filtro o bajar la frecuencia de sondeo del PCNT.
- Un paso = un evento; la UI decide si mover el foco, hacer scroll o cambiar de
  opción. Sin aceleración en v1: 20 muescas por vuelta son suficientes.

### 8.2. Botones A/B/PTT

- `INPUT_PULLUP`, activo a nivel bajo.
- Debounce por software de 20 ms; se registra el flanco de bajada y se espera
  la estabilidad antes de emitir.
- A/B: pulsación corta y larga. Larga = mantener 800 ms (interrumpir en
  `DETAIL`, confirmar en riesgo alto).
- PTT: solo cuenta mantener; al bajar se emite `PTT_DOWN`, al subir `PTT_UP`.
  Una pulsación de menos de 150 ms se descarta (evita dictados vacíos).
- No se usa `gpio_isr_handler` para rebotar directamente en la ISR: la ISR
  despierta `input_task` y allí se hace el debounce.

---

## 9. Red y protocolo

### 9.1. Conexiones

- Dos clientes `esp_websocket_client`: `/ws/control` (texto) y `/ws/audio`
  (binario).
- TLS con el certificado autofirmado del gateway embebido en el firmware
  (equivale a *pinning* por certificado). Sin CA pública.
- `hello` inmediato con `proto:1`, `device_id` y el token de NVS.
- Si el token es rechazado (4401), se borra de NVS y se pasa a emparejamiento;
  no se reintenta en bucle.

### 9.2. Estado y memoria

- Un `state_cache` con `agents[3]`, `system`, `seq`, `approvals[4]`.
- Se descartan estados con `seq` menor.
- Los strings se copian a buffers fijos (id 32, tarea 96, log 128, comando
  1024, `cwd` 160). Nada de punteros a JSON que se libera.
- El parseo usa `cJSON_ParseWithLength` y rechaza mensajes de más de 8 KB.
- Campos desconocidos se ignoran (el gateway ya los rechaza al revés).

### 9.3. Reconexión

- Backoff 1, 2, 4, 8, 16, 30 s con jitter.
- Al conectar: `welcome` → `state` → **aprobaciones pendientes**. El gateway ya
  las reenvía; el firmware debe encolarlas y mostrar la primera.
- `ping` cada 10 s; 3 sin `pong` → `OFFLINE` y reconexión.
- Si el gateway vuelve, se re-sincroniza sin reproducir eventos perdidos.

### 9.4. Errores

| Código | Acción |
|---|---|
| `invalid_token` | Borrar token, volver a emparejar |
| `proto_mismatch` | Mostrar «actualiza el firmware»; no reintentar en bucle |
| `unknown` / `invalid_option` | Cerrar la modal y pedir estado |
| `stt_not_configured` | Avisar «voz no disponible» y volver a `DETAIL` |
| `frame_too_large` | Reducir el frame de audio (no debería ocurrir con 20 ms) |
| Error de TLS | `OFFLINE`; no degradar a `ws://` |

---

## 10. Audio

### 10.1. Entrada (INMP441)

- I2S0 en modo RX, 16 kHz, mono, **slots de 32 bits**.
- El INMP441 entrega 24 bits alineados a la izquierda dentro del slot de 32;
  el PCM de 16 bits se obtiene con `(int16_t)(raw >> 16)`. Verificar el nivel
  con una grabación de prueba antes de dar por buena la escala.
- DMA: 4 descriptores × 320 muestras (20 ms). Los buffers DMA van en **RAM
  interna**; el anillo grande, en PSRAM.
- **Pre-roll de 200 ms**: se captura en continuo a un anillo pequeño y, al
  pulsar PTT, se envían también los 200 ms anteriores. Evita cortar la primera
  sílaba.
- **Streaming durante la pulsación**, no subida al soltar: cada 20 ms se envía
  un frame de 640 bytes por `/ws/audio`. Al soltar, `audio_end`. Así el gateway
  puede hacer VAD y transcribir antes, y no hay que retener 3 s en RAM.
- Límite de utterance: 30 s; al llegar, se corta y se envía `audio_end` con un
  aviso en pantalla.

### 10.2. Salida (MAX98357A)

- I2S1 en modo TX, 16 kHz, mono (el amplificador sintetiza el canal).
- Solo tonos generados en el dispositivo (LUT de seno, 16 bits):

| Evento | Tono |
|---|---|
| PTT empieza | 1,2 kHz, 30 ms |
| PTT termina | 800 Hz, 30 ms |
| Agente te necesita | 880 Hz × 2, 60 ms, pausa 80 ms |
| Permiso concedido | 1 kHz, 60 ms |
| Denegado / error | 220 Hz, 120 ms |
| Gateway caído | 440 Hz, 200 ms |

- `SD/EN` a bajo al arrancar y tras cada tono; se espera 5 ms antes de apagar
  para evitar el *pop*. Si aparece ruido o reinicio, condensador de 470 µF
  entre 5 V y GND junto al MAX98357A (ya previsto como contingencia).
- **Half-duplex**: mientras suena un tono no se graba; el micrófono se ignora.
- Sin TTS en v1. El día que se añada, el gateway envía PCM/Opus y el dispositivo
  solo reproduce; no sintetiza.

### 10.3. Máquina de estados del PTT

```text
IDLE --PTT_DOWN--> RECORDING --PTT_UP--> WAIT_TRANSCRIPT --transcript--> PREVIEW
  ^                    |                       |                           |
  |                    | 30 s                  | error                     | A
  |                    v                       v                           v
  +------------------ ABORT <---------------- OFFLINE                    SEND
```

- `PREVIEW` muestra el texto; A envía `inject_text` con `confirm: true`, B
  cancela, PTT regraba.
- Nunca se inyecta sin preview, ni siquiera si la confianza es alta.

---

## 11. Persistencia, aprovisionamiento y OTA

### 11.1. NVS

| Clave | Contenido |
|---|---|
| `wifi_ssid`, `wifi_pass` | Credenciales WiFi |
| `gw_host`, `gw_port` | Gateway (IP o mDNS) |
| `device_id` | `baton-XXXXXXXX`, generado una vez |
| `totp_secret` | Secreto TOTP persistente (20 bytes) |
| `pair_gw_id`, `pair_gw_url`, `pair_gw_name` | Gateway emparejado |
| `pair_token` | Token de emparejamiento |
| `pair_at`, `pair_rotate` | Fecha y política de rotación |
| `brightness`, `language` | Preferencias |
| `ota_url` | Origen del firmware |
| `app_valid` | Marca para el rollback de OTA |

El token se guarda en NVS sin cifrar en v1. Es aceptable si el dispositivo vive
en casa y la red es de confianza; si se vende, activar NVS cifrada con clave en
eFuse.

#### Primer arranque

- Si faltan `device_id` y `totp_secret`, se generan en el dispositivo con
  `esp_random()` / `esp_fill_random()` y se guardan en NVS. No hace falta
  precargar un secreto por unidad.
- El QR se pinta sin Wi-Fi y sin hora. La hora solo se necesita para verificar
  el código: la app la manda por USB o SNTP la obtiene al conectar.
- El secreto no se imprime, no se registra y no sale del dispositivo; solo se
  usa para pintar el QR en `PAIRING`.
- El borrado de fábrica regenera identidad y secreto; el Authenticator anterior
  deja de valer.
- Para un producto: Secure Boot v2 y Flash Encryption/NVS cifrada antes de
  enviar. Sin cifrado, `esptool read_flash` puede leer el secreto con acceso
  físico.

### 11.2. Aprovisionamiento WiFi

- Primer arranque sin credenciales → SoftAP `baton-XXXX` con portal cautivo.
- La pantalla muestra el SSID y `http://192.168.4.1`.
- Formulario: SSID, contraseña y **host del gateway** (IP o `baton.local`).
- Se guarda en NVS y se reinicia la conexión. Sin app móvil y sin BLE en v1.
- mDNS en el gateway (`_baton._tcp`) es un extra deseable, no un requisito.

### 11.3. Emparejamiento TOTP

El flujo actual del gateway asume que **el usuario teclea un código de 6 dígitos
en el dispositivo**. Con un encoder y tres botones eso es una tortura y no es lo
que dice la revisión técnica. El flujo de hardware es el inverso:

1. El dispositivo muestra un QR `otpauth://` (Google Authenticator) y un id
   corto.
2. El usuario escanea el QR y conecta el dispositivo al PC por USB.
3. La app pide el código de 6 dígitos, lo envía al dispositivo y este lo
   verifica.
4. La primera vez, el dispositivo muestra el nombre del PC y un SAS y el usuario
   pulsa **A**. En un reemplazo basta el código: aviso de 5 s y B para cancelar.
5. La app registra el dispositivo en el gateway y le entrega el token.
6. El dispositivo guarda **un solo** emparejamiento en NVS y conecta.

El secreto TOTP y el `device_id` viven en el dispositivo; el gateway nunca los
ve. Reemparejar en otro PC exige abrir la ventana (USB, reinicio o `A+B` 3 s) y
sustituye la ficha anterior. El diseño completo, mensajes, estados y amenazas
está en [`DISENO_EMPAREJAMIENTO_TOTP.md`](DISENO_EMPAREJAMIENTO_TOTP.md).

Esto es un **bloqueante de Fase C**: sin este cambio, el firmware no se puede
emparejar de forma usable. Hay que implementarlo en el gateway antes de la
primera prueba con hardware.

### 11.4. OTA

- Particiones `ota_0` y `ota_1` de 3,5 MB; el firmware no debe pasar de ~3 MB.
- Descarga por HTTPS desde el gateway o desde una URL configurada.
- Verificación SHA-256 antes de escribir; `esp_ota_end` + `esp_ota_set_boot_partition`.
- Tras el primer `welcome` correcto, `esp_ota_mark_app_valid_cancel_rollback()`.
  Si no conecta en 3 intentos, el bootloader vuelve a la versión anterior.
- La versión se anuncia en `hello.fw`; el gateway la registra en auditoría.

### 11.5. Particiones (16 MB)

| Partición | Tamaño | Uso |
|---|---:|---|
| `nvs` | 64 KB | Configuración y token |
| `otadata` | 8 KB | Selección OTA |
| `phy_init` | 4 KB | Calibración RF |
| `ota_0` | 3,5 MB | Aplicación A |
| `ota_1` | 3,5 MB | Aplicación B |
| `assets` | 8 MB | Fuentes, iconos, sonidos futuros |

Las fuentes de LVGL se compilan en `rodata` (van en la app); `assets` queda para
imágenes y sonidos que no convenga meter en el binario.

---

## 12. Seguridad

- El dispositivo **nunca** ve API keys de agentes ni contenido de prompts.
- Token en NVS; TLS con certificado del gateway embebido.
- El gateway escucha en la LAN; el panel de administración sigue en loopback.
- LED de micrófono encendido mientras se graba (GPIO 42) y, en la versión final,
  interruptor físico de mute en serie con la alimentación del INMP441.
- No se aceptan comandos por HTTP en el dispositivo; solo la UI local.
- El firmware no implementa `ws://` en claro: si no hay TLS, no conecta.
- El QR de emparejamiento solo se muestra en modo emparejamiento (120 s), caduca
  y exige confirmación física con A.

---

## 13. Rendimiento y presupuesto

| Etapa | Objetivo | Nota |
|---|---|---|
| Input → evento en cola | < 5 ms | ISR + tarea |
| Render de un frame parcial | 20–30 ms | 480×40 a 40 MHz |
| Cambio de pantalla | < 120 ms | Dos buffers parciales |
| Aprobación ida y vuelta LAN | < 150 ms | Control separado del audio |
| PTT suelto → texto en pantalla | p95 < 1,5 s | Depende del STT del gateway |
| Reconexión tras caída | < 5 s | Backoff inicial |
| Arranque a dashboard | < 3 s | Con WiFi ya configurado |

Consumo estimado: 350 mA de media con WiFi y pantalla al 50 %; picos de
0,9–1,2 A con el amplificador a 1 W. Fuente de 5 V/2 A y 470 µF junto al
amplificador.

---

## 14. Pruebas

### 14.1. En host (sin hardware)

- Parseo/serialización del protocolo con los mismos JSON del gateway.
- Máquina de estados de la UI y del PTT con eventos sintéticos.
- Decodificación del encoder (secuencias con rebote).
- Cola de aprobaciones: caducidad, `stale`, duplicados.
- Anillo de audio: pre-roll, límite de 30 s, frames de 20 ms.

Se compilan como un target `linux` de ESP-IDF o con Unity en el PC, sin tocar
drivers.

### 14.2. En banco

| Prueba | Criterio |
|---|---|
| Pantalla | 20–30 fps en refresco parcial; sin *tearing* |
| Encoder | 100 muescas/s sin pérdidas ni dobles pasos |
| Botones | 100.000 pulsaciones; debounce estable |
| PTT | 10.000 pulsaciones; sin dictados vacíos |
| Audio | 10 frases es/ca/en; sin clipping; nivel correcto |
| WiFi | Caída y reconexión < 5 s; RSSI con pantalla y amp encendidos |
| Aprobaciones | 1.000 aprobaciones; 0 ejecuciones dobles |
| Soak | 72 h con ciclos de estado y reconexiones |
| Alimentación | Sin brownout a 4,75 V con picos del amplificador |
| OTA | Actualización y rollback forzado |

### 14.3. En mecánica

- 10.000 ciclos de bisagra (cuando exista).
- 100.000 pulsaciones de A/B/PTT.
- 10.000 detents del encoder.
- Caída de 1 m sobre las esquinas.

---

## 15. Fases del firmware

| Fase | Entregable | Criterio de salida |
|---|---|---|
| F1. BSP | Display, encoder, A/B/PTT, mic, amp, WiFi | Todo responde desde `app_main` |
| F2. UI + control | Pantallas, grupos LVGL, WSS JSON, modal | Aprobar/denegar desde el dispositivo con el agente falso |
| F3. Audio | PTT streaming, preview, tonos | p95 < 1,5 s; 100 dictados sin bloqueo |
| F4. Resistencia | Aprovisionamiento, emparejamiento invertido, OTA, WDT | 72 h; OTA con rollback |
| F5. Mecánica | Carcasa, encoder, bisagra, cable | 10.000 ciclos; uso diario 2 semanas |

F2 no espera al STT: se puede validar el flujo completo de estado y aprobación
con el agente falso que ya existe. F3 sí depende de la fase 0.5 del gateway
(STT real o un transcript simulado de desarrollo).

---

## 16. Decisiones abiertas y riesgos

| Tema | Estado | Riesgo |
|---|---|---|
| Emparejamiento invertido | **Pendiente en el gateway** | Bloquea F2/F4 si no se hace |
| Dos WebSockets con TLS | Provisional | 50–80 KB de RAM; si aprieta, un socket con frames tipados |
| Certificado autofirmado | Diseñado | Hay que regenerarlo por instalación y reflashearlo o provisionarlo |
| Encoder push | Reservado en GPIO40 | No se usa en v1 |
| GPIO48 (LED RGB) | Verificar placa | Colisión con el botón B si la placa lo usa |
| `>> 16` en INMP441 | Verificar con audio | Nivel 64× bajo si el alineamiento es otro |
| Dos TLS + LVGL | Presupuesto ajustado | Medir `heap_caps_get_largest_free_block()` en F1 |

---

## 17. Lo que hay que cambiar en el gateway antes de F2

1. **Emparejamiento invertido** (`/api/pair/request`, aprobación desde el panel,
   entrega del token al dispositivo). Es el bloqueante principal.
2. **Transcript de desarrollo** (`BATON_FAKE_STT` o similar) para probar la UI de
   dictado antes de que exista `faster-whisper`, sin inventar transcripciones en
   producción.
3. **Endpoint de OTA** (`/api/firmware/latest` + binario + SHA-256) para F4.
4. **mDNS** `_baton._tcp` para no teclear la IP del gateway en el portal.
5. Registrar `fw` y `device_id` en la auditoría al conectar (ya se guarda el
   dispositivo; falta la versión de firmware).
