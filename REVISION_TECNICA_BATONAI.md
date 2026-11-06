# Revisión técnica de la especificación batonAI

**Documento revisado:** `especificaci_n_t_cnica_batonai.md` (v1, 171 líneas)
**Fecha:** 4 de noviembre de 2026
**Veredicto:** concepto viable y bien enfocado, pero hay **6 decisiones de diseño que, tal como están escritas, no se sostienen**. La más importante: el sistema no debe depender de *scraping* de PTY ni de un botón que inyecta `y\n` sin contexto.

---

## 0. Resumen ejecutivo

batonAI tiene una buena tesis: un mando físico de sobremesa, sin distraer la pantalla principal, para vigilar agentes y resolver bloqueos. El hardware es asequible, el firmware es razonable para un ESP32-S3 y la separación dispositivo/gateway es correcta.

El problema no es el concepto, sino **cómo se conecta con los agentes** y **cómo se aprueban acciones peligrosas**. La especificación promete un sistema "agnóstico" mediante PTY, pero los agentes reales son TUIs con ANSI, prompts que cambian entre versiones y, en Windows, requieren ConPTY. Eso convierte el *scraping* en el componente más frágil del proyecto. La buena noticia: Claude Code y OpenCode ya exponen mecanismos nativos de permisos que encajan casi perfectamente con batonAI.

### Hallazgos principales

| # | Severidad | Hallazgo | Corrección propuesta |
|---|---|---|---|
| 1 | **Crítica** | `[A]` inyecta `y\n` sin saber a qué aprobación corresponde. Una pulsación tardía o repetida puede aprobar un comando destructivo distinto. | `approval_id` único, comando completo en pantalla, política de riesgo, *hold-to-confirm* y timeout que deniega. |
| 2 | **Crítica** | El "agnosticismo" vía PTY y detección de `[y/N]` es frágil: TUIs, alternate screen, prompts variables, Windows sin `pty`. | Arquitectura de **adaptadores**: hooks/API nativos primero, PTY solo como *fallback*. |
| 3 | **Alta** | "El proxy calcula los tokens antes de reenviarlos" es imposible: los tokens de salida se conocen al final, y el streaming no los expone antes. | Proxy transparente + lectura de `usage` en la respuesta/SSE + tabla de precios. |
| 4 | **Alta** | `<300 ms` de transcripción no es un presupuesto realista de extremo a extremo. `faster-whisper` no es streaming y requiere VAD, modelo caliente y, idealmente, GPU. | Presupuesto p95 < 1,5 s tras soltar PTT; VAD + *utterance* completa; modelo caliente; preview del texto. |
| 5 | **Crítica** | WebSocket en LAN sin autenticación: cualquier dispositivo de la red puede aprobar comandos o inyectar texto. | Pairing, token por dispositivo, TLS con certificado fijado, auditoría y *fail-closed* en acciones. |
| 6 | **Alta** | Bisagra de 3DS con paso de cables + FPC SPI: probablemente no cabe, no mantiene ángulo continuo y el FPC sufre fatiga. | Bisagra de fricción tipo portátil con canal de 7–8 mm, o cable en lazada entre dos bisagras; ensayo de 10.000 ciclos. |
| 7 | Media | 480×320 por SPI y 4,0" no dan 60 fps; el presupuesto de GPIO del N16R8 es más ajustado de lo que parece. | 3,5" SPI para v1, refresco parcial LVGL, buffers en RAM interna, mapa de pines explícito. |

**Recomendación:** mantener el hardware y el concepto, pero reescribir las secciones 2, 5 y 6 alrededor de un **modelo de aprobaciones con identidad** y una **capa de adaptadores por agente**. Eso reduce el riesgo técnico más que cualquier cambio de pantalla o de carcasa.

---

## 1. Lo que está bien y conviene conservar

- **Formato clamshell de sobremesa.** Es un acierto frente a una tablet o un móvil: pantalla inclinada, controles ciegos y un sitio fijo.
- **Pantalla no táctil.** Abarata, simplifica el firmware y evita huellas; el D-pad es suficiente para una UI de estados.
- **Gateway local.** Mantiene las credenciales y el audio en el PC, y permite que el dispositivo sea tonto y barato.
- **Push-to-talk.** Es la interacción correcta para dictado; un wake word sería más frágil y peor para la privacidad.
- **Semáforo de estados.** `RUNNING / WAITING_INPUT / DONE / ERROR` es un buen resumen mental; solo hay que precisar las transiciones.
- **ESP32-S3 N16R8 + LVGL + I2S.** Combinación probada, con margen para OTA, fuentes y buffers.
- **Fase 0 software primero.** Es el orden correcto: el 80 % del riesgo está en el gateway, no en la carcasa.

---

## 2. Hallazgos críticos en detalle

### C1. El botón `[A]` no puede inyectar `y\n` a ciegas

La especificación dice:

> Botón `[A]`: Inyecta `y\n`.
> Botón `[B]`: Inyecta `n\n` o interrupción `Ctrl+C`.

Eso funciona en un menú de consola simple, pero falla en el caso real:

1. El agente A pide confirmación para `npm run test`.
2. El dispositivo muestra el modal.
3. El usuario se distrae; el agente A recibe `Ctrl+C` del PC o termina.
4. El agente B pide confirmación para `rm -rf build/`.
5. El usuario pulsa `[A]` creyendo que aprueba los tests.
6. Se aprueba el borrado.

También hay riesgo de **repetición de tecla**, **doble pulsación** por rebote y **pulsación accidental** al coger el dispositivo. Un mando físico que aprueba comandos destructivos necesita más ceremonia que un `y\n`.

**Diseño propuesto:**

- Cada solicitud lleva un `approval_id` (UUID) y el gateway **rechaza respuestas que no correspondan a la solicitud activa**.
- La pantalla muestra: agente, `cwd`, comando completo (no truncado a una línea), tipo de operación y tiempo restante.
- **Riesgo normal:** pulsación simple de `[A]`.
- **Riesgo alto** (`rm -rf`, `git push --force`, `DROP`, `sudo`, escritura fuera del repo, `curl | sh`): mantener `[A]` 1,5 s con anillo de progreso; o `[B]` seguido de `[A]`. Nunca un solo toque.
- **Timeout** (p. ej. 60 s): la solicitud caduca, se deniega o se deja el prompt en el PC; jamás se auto-aprueba.
- `[B]` significa "no" para esa aprobación. `Ctrl+C` debe ser una acción separada ("interrumpir agente"), no el significado por defecto de "no": matar el proceso no es lo mismo que responder que no.
- El resultado (`accepted`, `rejected`, `expired`, `stale`) se devuelve al dispositivo y se registra.

> Regla de oro: **el dispositivo propone, el gateway decide y el agente confirma**. La pantalla nunca es la única fuente de verdad.

### C2. "Agnóstico vía PTY" es el punto más frágil

La especificación asume que se puede leer la salida de una terminal, detectar `[y/N]` o `?` y escribir en `stdin`. En la práctica:

- Los agentes son **TUIs** (Claude Code, OpenCode, Codex) que usan *alternate screen*, posicionamiento de cursor, colores y redibujados parciales. Un `readline()` de la salida no reconstruye la pantalla.
- Los prompts **cambian entre versiones** y entre modos (permiso de Bash, edición de ficheros, MCP, plan mode). No hay un `[y/N]` universal.
- En **Windows**, el módulo `pty` de la biblioteca estándar no existe; hay que usar ConPTY (`pywinpty`) o WSL. Claude Code en Windows puede usar PowerShell o Git Bash, con comportamientos distintos.
- El timing importa: escribir `y\n` mientras la TUI está redibujando puede perder la tecla o enviarla al prompt equivocado.

**Arquitectura propuesta: adaptadores, no un parser universal.**

```text
AgentAdapter (interfaz común)
  start(config) -> Session
  events() -> AgentEvent        # status, log, approval_request, usage
  respond(approval_id, decision)
  send_text(text)
  interrupt()
```

Implementaciones, por orden de preferencia:

| Agente | Integración recomendada | Qué permite |
|---|---|---|
| **Claude Code** | Hook HTTP `PermissionRequest` + hooks `Notification`, `Stop`, `PostToolUse` | Permiso con `allow`/`deny` en nombre del usuario, sin scraping; el hook puede esperar la respuesta del dispositivo. |
| **OpenCode** | `opencode serve` + SSE `/event` + `POST /session/:id/permissions/:permissionID` | Eventos de sesión, estado y respuesta a permisos por API; el TUI sigue funcionando. |
| **Codex** | Modo `exec` con salida JSON / app-server JSON-RPC (según versión) | Eventos estructurados y política de aprobación; fijar la versión soportada. |
| **Antigravity / IDE** | API si existe; si no, PTY/UI | No prometer soporte nativo hasta verificarlo. |
| **Genérico** | PTY + `pyte` (buffer de pantalla) + regex configurable | Último recurso, no la base del producto. |

**Claude Code, en concreto:** el hook `PermissionRequest` se ejecuta justo cuando el agente va a pedir permiso y puede devolver `{"decision": {"behavior": "allow" | "deny"}}`. Un hook HTTP puede quedarse esperando la respuesta del dispositivo. Si el gateway no está disponible, conviene **dejar que aparezca el prompt local** (no auto-aprobar), con `onFailure: "continue"` y un timeout razonable. Eso convierte a batonAI en un mando remoto del diálogo nativo, no en un sustituto frágil.

**OpenCode, en concreto:** el servidor expone `GET /event` (SSE) y `POST /session/:id/permissions/:permissionID` con `{response, remember?}`. Es exactamente el flujo que necesita batonAI, y además permite `prompt_async` para inyectar texto. Protege el servidor con `OPENCODE_SERVER_PASSWORD`.

**Consecuencia para la especificación:** eliminar la promesa de "sin cambios en el código de las herramientas". Para Claude Code y OpenCode **sí hay que instalar un hook/plugin o arrancar el servidor**, y eso está bien: es una configuración de cinco minutos a cambio de eliminar el componente más frágil.

### C3. El proxy de costes no puede "calcular tokens antes de reenviar"

La frase:

> El proxy calcula los tokens consumidos en cada chunk de respuesta antes de reenviarlos a la API externa oficial.

mezcla dos cosas:

1. **Tokens de entrada:** se pueden contar antes, con el tokenizador correcto del modelo (no es trivial: Anthropic, OpenAI y modelos locales usan tokenizadores distintos).
2. **Tokens de salida:** no existen hasta que el modelo los genera. En streaming, el proxy ve *chunks* de texto, pero no sabe el total hasta el final. Contar "a ojo" con `tiktoken` para un modelo Anthropic da cifras incorrectas.

**Diseño correcto:**

- El proxy reenvía la petición tal cual (sin modificar el cuerpo) y **lee el campo `usage` de la respuesta**.
- Anthropic Messages API: `message_start.message.usage` trae `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`; `message_delta.usage` trae `output_tokens`.
- OpenAI Chat Completions: añadir `stream_options: {"include_usage": true}` para recibir el `usage` final; en Responses API el campo cambia.
- Precios en una tabla configurable por modelo, con multiplicadores de caché y *reasoning tokens*.
- Distinguir **"coste API equivalente"** de **"gasto real"**: con suscripciones (Claude Max, ChatGPT, OpenCode Go) el coste calculado es informativo, no una factura.
- Soportar las rutas que usan de verdad: `/v1/messages`, `/v1/messages/count_tokens`, `/v1/chat/completions`, `/v1/responses`. No asumir que todas las herramientas hablan el mismo dialecto.
- **Cuidado con las URLs base:** `ANTHROPIC_BASE_URL` suele apuntar al host sin `/v1` (el SDK añade `/v1/messages`), mientras que `OPENAI_BASE_URL` normalmente **sí** incluye `/v1`. La especificación usa `http://localhost:8080/v1` para ambos; eso puede producir `/v1/v1/messages`. Documenta una URL distinta por proveedor.
- No registrar prompts/respuestas completas por defecto: solo metadatos de uso, para no crear un log sensible innecesario.

**Alternativa que reduce trabajo:** usar las métricas nativas. Claude Code puede exportar métricas por OpenTelemetry (verifica la versión); OpenCode incluye tokens/coste en los mensajes de sesión. Si esas fuentes están disponibles, el proxy deja de ser imprescindible y se convierte en un complemento para herramientas que no las expongan.

### C4. `<300 ms` de STT: cierto solo en el mejor caso

`faster-whisper` es **batch**, no streaming. Para transcribir necesita una *utterance* completa (o chunks con solapamiento), y el tiempo real depende de:

- modelo (`tiny`/`base`/`small`/`large-v3-turbo`), precisión (int8/float16) y hardware (GPU CUDA vs CPU);
- si el modelo ya está cargado y caliente (la primera inferencia tarda mucho más);
- VAD y *endpointing* (decidir cuándo el usuario ha terminado);
- resampling y limpieza de audio;
- cola de trabajos si hay varias pulsaciones seguidas.

Presupuesto realista:

| Escenario | Latencia de transcripción (3 s de audio) |
|---|---|
| GPU, `small`/`large-v3-turbo`, modelo caliente | ~150–400 ms |
| CPU moderna, `small` int8 | ~0,8–2 s |
| CPU, `base` int8 | ~0,4–1 s |
| API cloud (Deepgram/OpenAI) | ~300–800 ms + red |

Por tanto, el objetivo debe ser **p95 < 1,5 s desde que se suelta PTT hasta que el texto está listo**, no 300 ms. Y hay que mostrar el estado "transcribiendo" en la pantalla, porque la espera sin feedback se percibe como un fallo.

**Recomendaciones:**

- PTT + VAD local (Silero VAD o WebRTC VAD) y enviar una *utterance* completa, no un chorro continuo. Es más simple y más preciso.
- Modelo caliente al arrancar el gateway; GPU si está disponible; fallback a CPU.
- `language` configurable (`es`, `ca`, `en` o auto) y `initial_prompt` con vocabulario del proyecto (nombres de repos, comandos, siglas). Mejora mucho la precisión en dictado técnico.
- **Nunca inyectar el texto automáticamente.** Mostrar la transcripción en el dispositivo, con `[A]` para enviar y `[B]` para cancelar/editar. Un error de STT en un prompt de agente puede desencadenar acciones destructivas; el preview es barato y evita sustos.
- Si se quiere dictado continuo, usar un modelo realmente streaming (sherpa-onnx, Vosk) o un servicio streaming; no forzar `faster-whisper` a hacer something para lo que no está diseñado.

### C5. Seguridad: el WebSocket actual es una puerta abierta

La especificación no menciona autenticación. En una LAN compartida (oficina, piso compartido, coworking), cualquier dispositivo puede:

- conectarse a `:8765` y enviar `agent_action` con `"CONFIRM"` para cualquier agente;
- inyectar texto arbitrario en una terminal;
- escuchar el audio del micrófono si el servidor lo reenvía;
- cambiar el estado que ve el dispositivo.

**Medidas mínimas:**

1. **Pairing:** el dispositivo muestra un código de 6 dígitos; el gateway lo valida y emite un token por dispositivo, guardado en NVS. Sin token, no hay WebSocket.
2. **TLS:** `wss://` con certificado autofirmado generado en la instalación y *fingerprint* fijado en el dispositivo. En LAN no sustituye al token, pero evita sniffing y ataques triviales.
3. **Autorización por acción:** el gateway comprueba que el `approval_id` existe, está activo y pertenece al agente; rechaza duplicados (idempotencia).
4. **Auditoría:** SQLite con `ts`, `device_id`, `agent_id`, `approval_id`, comando, decisión, transcripción (o su hash) y resultado. Exportable.
5. **Límites:** tamaño máximo de frame, rate limit, validación de esquema (Pydantic), rechazo de campos desconocidos.
6. **Privacidad:** LED de micrófono activo, interruptor físico de mute en serie con la alimentación del INMP441, STT local por defecto.
7. **Secretos:** las API keys viven solo en el PC; el ESP32 nunca las ve.
8. **Superficie:** el gateway escucha solo en la interfaz LAN necesaria; nada de port forwarding; el panel de administración, en `127.0.0.1`.

No hace falta un sistema empresarial, pero sí **cerrar el camino "aprobar comandos sin autenticar"** antes de usar el dispositivo en una red real.

### C6. Bisagra y paso de cables: el riesgo mecánico subestimado

La especificación pide:

> Par de bisagras de torsión/fricción cilíndricas (repuesto 3DS/DS Lite) con retención de ángulo entre 0° y 135° con paso de cable.

Tres problemas:

1. **Las bisagras de 3DS no son de fricción continua.** Suelen tener muelle y posiciones (detents), no un ángulo ajustable arbitrario. Puede que no mantengan la tapa a 105° con el peso de un panel de 4" y una carcasa impresa.
2. **El paso de cables es estrecho.** Un FPC de 10 contactos a 0,5 mm mide ~5,5–6 mm de ancho; la luz interior de una bisagra de 3DS es menor. Un cable de 10 hilos tampoco pasa bien. Si además el FPC va justo, el radio de curvatura en cada apertura es pequeño y el cobre se fatiga.
3. **La rigidez del conjunto.** La tapa con pantalla y bisagra barata puede cabecear; en un dispositivo de escritorio se nota mucho.

**Opciones, de mejor a peor:**

- **Bisagra de fricción tipo portátil** (eje de 6–8 mm, par 0,3–0,6 N·m) con un nudillo impreso que deje un canal de 7–8 mm para el cable. Es la solución más robusta y permite ángulo continuo.
- **Dos bisagras separadas** con el cable en lazada entre ambas, no a través del eje. La lazada trabaja a flexión, no a torsión, y se puede guiar con una pieza de radio amplio.
- **Cable externo con funda trenzada** entre tapa y base. Menos elegante, pero robusto y fácil de reparar.
- **FPC de 6 pines** solo si se reduce el número de señales (por ejemplo, SPI de 3 hilos + alimentación), lo cual no es trivial con una pantalla que necesita `CS`, `DC`, `RST` y `BL`.

**Especificación mecánica que falta:**

- Radio de curvatura mínimo del cable: ≥5× el espesor, y nunca un doblez a 90° sobre el eje.
- Alivio de tensión en ambos extremos y holgura de servicio.
- Ensayo de 10.000 ciclos de apertura/cierre con monitorización de continuidad.
- Tolerancias de impresión (0,2 mm), inserts roscados M2,5, tornillos y topes.
- La antena del ESP32 y el FPC de la pantalla no deben quedar enfrentados ni cerca de metal.

### C7. Pantalla, SPI y presupuesto de GPIO

**Ancho de banda.** Una imagen de 480×320 en RGB565 son 307.200 bytes. Por SPI a 40 MHz (≈5 MB/s teóricos, menos con overhead) un refresco completo tarda ~60–80 ms: **12–16 fps**. A 80 MHz se puede duplicar, pero el cable a través de la bisagra empeora la integridad de señal. Para un dashboard con refresco parcial de LVGL es suficiente; para animaciones a 60 fps, no.

**Recomendación:** 3,5" 480×320 SPI (ST7796/ILI9488) para la v1. Los paneles de 4,0" de 480×320 SPI existen, pero son menos comunes; muchos 4,0" son RGB de 40 pines, que consumen 16+ GPIO y dependen del ancho de banda de PSRAM. No es un cambio que convenga hacer sin necesidad.

**Buffers LVGL.** No poner el framebuffer completo en PSRAM: usa dos buffers parciales de 480×40 en RAM interna DMA (~38 KB cada uno) y `lv_display_flush_ready()` al terminar la transferencia. El resto de assets (fuentes, iconos) puede vivir en flash/PSRAM.

**GPIO del N16R8.** El módulo usa flash interna en GPIO26–32 y PSRAM octal en GPIO33–37; además, GPIO19/20 son USB y GPIO0/3/45/46 son *strapping*. Quedan ~25 pines utilizables, y el diseño necesita ~23. Es factible, pero **no hay margen para improvisar**. Verifica el pinout exacto de tu placa: algunos DevKitC-1 llevan un LED RGB en GPIO48 o GPIO38 que puede colisionar.

Mapa de pines propuesto (a validar con la placa concreta):

| Función | GPIO | Notas |
|---|---|---|
| LCD SCLK | 12 | SPI2 |
| LCD MOSI | 11 | SPI2 |
| LCD CS | 10 | |
| LCD DC | 9 | |
| LCD RST | 8 | |
| LCD BL | 7 | LEDC PWM |
| Mic SCK | 4 | I2S0 |
| Mic WS | 5 | I2S0 |
| Mic SD | 6 | I2S0 |
| Amp BCLK | 15 | I2S1 |
| Amp LRC | 16 | I2S1 |
| Amp DIN | 17 | I2S1 |
| Amp SD/EN | 18 | mute al arrancar |
| D-pad ↑↓←→ | 38, 39, 40, 41 | pulsadores a GND |
| Botón A | 47 | |
| Botón B | 48 | verifica LED RGB de la placa |
| PTT | 21 | pulsador grande |
| Stick X / Y | 1 / 2 | ADC1, con filtro RC |
| Haptic (opcional) | 42 | MOSFET |
| I2C expansor (opcional) | 13 / 14 | si faltan pines |

Si el stick analógico no es imprescindible, un D-pad de 5 pulsadores es más robusto para uso a ciegas y libera dos pines/ADC. La especificación debería decidir entre "D-pad **o** stick", no ambos.

---

## 3. Hallazgos medios y detalles que faltan

### 3.1. Protocolo

El JSON de ejemplo es un buen punto de partida, pero le faltan campos que se necesitan el primer día:

- `proto_version`, `seq`, `ts` (ISO 8601 UTC), `device_id`.
- `approval_id`, `expires_at`, `risk`, `cwd`, `command` completo (no solo `message`).
- `ack` de acciones y `error` con código.
- `ping`/`pong` y reconexión con *backoff*.
- Separar `prompt` (lo que pide el agente) de `last_log` (última línea de terminal).
- Enums cerrados y validación de esquema.

Además, **separa audio y control en dos WebSockets** (`/ws/control` y `/ws/audio`) o, como mínimo, marca los frames binarios con un byte de tipo. Un chunk de audio grande en la misma conexión puede retrasar la llegada de un `approval_request`; en un mando de aprobación, la latencia del control es lo que más importa.

Formato binario sugerido:

```text
byte 0      : 0x01 = audio PCM
bytes 1..4  : seq (uint32 LE)
bytes 5..N  : PCM 16-bit LE, mono, 16 kHz
```

Y mensajes de ciclo de vida:

```json
{"type":"audio_start","agent_id":"claude-code","sample_rate":16000,"format":"s16le","channels":1}
{"type":"audio_end","seq":42,"duration_ms":3200}
```

Sin `audio_start`/`audio_end`, el gateway no sabe cuándo empieza y acaba una *utterance* y no puede hacer VAD correctamente.

### 3.2. Modelo de estados

`DONE` es ambiguo: un agente puede terminar una tarea y seguir vivo esperando la siguiente. Propongo:

| Estado | Significado | Transición |
|---|---|---|
| `IDLE` | vivo, sin tarea | → `RUNNING` |
| `RUNNING` | procesando o ejecutando herramientas | → `WAITING_INPUT`, `IDLE`, `ERROR` |
| `WAITING_INPUT` | bloqueado esperando al usuario | → `RUNNING` (aprobado), `IDLE` (denegado), `ERROR` |
| `DONE` | tarea completada (no necesariamente el proceso) | → `IDLE` |
| `ERROR` | fallo de ejecución | → `IDLE` tras revisión |
| `OFFLINE` | sin heartbeat | → `IDLE` al reconectar |

Cada agente debería llevar `since`, `last_event_at`, `approval_id` (si aplica), `model`, `cwd` y `cost_turn`/`cost_session`.

### 3.3. UI/UX

- En 480×320 caben **2–3 tarjetas** legibles, no una lista larga. Prioriza `WAITING_INPUT` arriba y con sonido/háptica, no solo parpadeo.
- No uses solo color: añade icono y forma (`▶`, `⏸`, `✓`, `✗`) para daltonismo.
- Tipografía mínima de 16 px para estados y 13–14 px monoespaciada para logs; incluye acentos y `€` en el subset de la fuente (`lv_font_conv` con Latin-1).
- El modal debe ocupar la pantalla, mostrar el comando completo con *scroll* y el `cwd`, y tener un contador de tiempo.
- La transcripción de voz se muestra antes de enviar; `[A]` envía, `[B]` cancela.
- Añade pantalla de "gateway desconectado" con la antigüedad del último estado; no dejes la última telemetría congelada como si fuera actual.
- Para uso a ciegas: `[A]` convexo, `[B]` cóncavo, `[PTT]` con anillo/textura; separación ≥18 mm; PTT accesible con el pulgar sin mirar.
- Añade brillo ajustable, volumen y un modo "no molestar" para las alertas.

### 3.4. Alimentación y audio

- Pico estimado: ESP32-S3 con WiFi ~350 mA + retroiluminación ~100–150 mA + amplificador a 1 W ~400 mA + pérdidas ≈ **0,9–1,2 A a 5 V**. Usa fuente de 5 V/2 A, fusible rearmable de 1,5 A y condensador de 470–1000 µF junto al amplificador.
- El MAX98357A puede hacer *pop* al encenderse; usa el pin `SD`/`EN` para silenciarlo durante el arranque.
- Micrófono y altavoz comparten carcasa: usa **half-duplex** (silencia el micrófono mientras suena el altavoz) y separa físicamente ambos con espuma/goma. Sin cancelación de eco, el TTS se colará en el micrófono.
- Coloca el INMP441 en el borde superior de la base, con orificio de 1 mm y junta acústica, lejos del altavoz y del regulador.
- Mantén 15 mm de zona libre alrededor de la antena del ESP32; el FPC de la pantalla y el amplificador no deben pasar por encima.

### 3.5. BOM: faltan cosas y el coste es optimista

La tabla de la especificación suma 35–53 €, pero omite cableado, conectores, alimentación, tornillería, inserts, patas, PCB/protoboard, envío e impuestos. Un presupuesto realista para una unidad es **60–100 €** (sin contar herramientas).

| Partida | Coste realista (€) | Nota |
|---|---|---|
| ESP32-S3 DevKitC-1 N16R8 | 10–14 | |
| LCD 3,5" SPI 480×320 | 15–20 | 4,0" añade 5–10 € y riesgo |
| INMP441 | 2–4 | módulo clónico; prevé alternativa |
| MAX98357A + altavoz 8 Ω 1 W | 4–7 | altavoz en recinto sellado |
| D-pad/stick + 2 Choc + PTT + keycaps | 8–12 | |
| Bisagras + eje/tornillería | 5–10 | |
| FPC/cable, conectores, alivio | 4–8 | |
| Alimentación (USB-C, interruptor, fusible, caps) | 4–7 | |
| Carcasa impresa (filamento, fallos) | 4–8 | |
| Tornillería, inserts, patas | 3–5 | |
| PCB/protoboard y cableado | 4–8 | |
| Envío, aduanas, impuestos | 10–20 | |
| **Total** | **~73–123** | según proveedor y 3,5"/4,0" |

No es un problema para un DIY, pero conviene que la especificación no prometa 35 €.

### 3.6. Windows

- `pty` no existe en Windows: usa `pywinpty` (ConPTY) o ejecuta el gateway en WSL. Claude Code en Windows puede usar PowerShell o Git Bash; los hooks de ejemplo de la documentación ya contemplan PowerShell.
- Prueba las dos rutas (nativo y WSL) antes de fijar la arquitectura; los paths, señales y códigos de salida cambian.
- El instalador debería registrar el gateway como servicio (NSSM o Tarea Programada) y ofrecer un icono de bandeja con estado, logs y "abrir panel".

### 3.7. Lo que falta en la hoja de ruta

- **Aprovisionamiento WiFi** (portal cautivo + NVS) y **OTA** con rollback. Con 16 MB hay espacio para dos particiones OTA.
- **Protocolo versionado** y pruebas de compatibilidad.
- **Auditoría** y política de retención de logs.
- **Ensayo de fiabilidad**: 72 h, reconexiones, WiFi caído, gateway reiniciado, 1.000 aprobaciones.
- **Ensayo mecánico**: 10.000 ciclos de bisagra, caída de 1 m, pulsaciones de 100.000 ciclos.
- **Ensayo de audio**: español/catalán/inglés, ruido de fondo, distancia de 20–60 cm, medir WER.
- **Ensayo de potencia/EMC**: corriente pico, brownout, RSSI con pantalla y amplificador encendidos.
- **Documentación de montaje** y lista de materiales con enlaces y alternativas.

---

## 4. Arquitectura revisada

```text
┌──────────────────────────────┐
│ Dispositivo batonAI          │
│  LVGL + input + I2S + WiFi   │
└──────────────┬───────────────┘
               │ WSS control (JSON)   WSS audio (PCM)
               ▼
┌──────────────────────────────────────────────────────────┐
│ Gateway local                                            │
│                                                          │
│  DeviceHub        ApprovalBroker       AuditLog          │
│  auth, seq,       approval_id,         SQLite, export    │
│  state cache      risk, timeout                          │
│                                                          │
│  AgentRegistry                                           │
│   ├─ ClaudeCodeAdapter  (hooks HTTP)                     │
│   ├─ OpenCodeAdapter    (server SSE + permissions API)   │
│   ├─ CodexAdapter       (exec JSON / app-server)         │
│   └─ GenericPtyAdapter  (pyte, último recurso)           │
│                                                          │
│  UsageCollector   (usage nativo / proxy / OTel)          │
│  STTService       (VAD + faster-whisper, modelo caliente)│
│  Config UI        (localhost, solo administración)       │
└──────────────────────────────────────────────────────────┘
```

**Principios:**

1. El gateway es la única fuente de verdad; el ESP32 solo renderiza y captura input.
2. Toda aprobación tiene identidad (`approval_id`), riesgo y caducidad.
3. Los adaptadores normalizan eventos; el dispositivo no sabe si el agente es Claude, OpenCode o un PTY.
4. El audio va por un canal separado y el control nunca espera al audio.
5. Si el gateway cae, el PC sigue funcionando con sus prompts locales; el dispositivo muestra `OFFLINE`.

---

## 5. Protocolo v1 propuesto

### 5.1. Conexión y autenticación

```json
{"type":"hello","proto":1,"device_id":"baton-01","fw":"0.1.0","token":"<pairing-token>"}
{"type":"welcome","session_id":"...","server_time":"2026-11-04T10:00:00Z","config":{"heartbeat_s":10,"approval_timeout_s":60}}
```

### 5.2. Estado

```json
{
  "type": "state",
  "seq": 128,
  "ts": "2026-11-04T10:00:01Z",
  "system": {
    "total_cost": 0.384,
    "total_tokens": 42100,
    "active_agents": 2,
    "waiting_agents": 1
  },
  "agents": [
    {
      "id": "claude-code",
      "name": "Claude Code",
      "provider": "anthropic",
      "model": "claude-sonnet-4-5",
      "status": "WAITING_INPUT",
      "since": "2026-11-04T09:59:40Z",
      "cwd": "C:\\dev\\proyecto",
      "task": "Refactorizar autenticación",
      "cost_turn": 0.21,
      "cost_session": 0.21,
      "approval_id": "apr_7f3c...",
      "prompt": "¿Ejecutar 'npm run test'?",
      "risk": "normal"
    }
  ]
}
```

### 5.3. Aprobación

```json
{
  "type": "approval_request",
  "approval_id": "apr_7f3c...",
  "agent_id": "claude-code",
  "kind": "bash",
  "title": "Ejecutar comando",
  "command": "npm run test",
  "cwd": "C:\\dev\\proyecto",
  "risk": "normal",
  "expires_at": "2026-11-04T10:01:40Z",
  "options": [
    {"id": "allow", "label": "Sí", "key": "A"},
    {"id": "deny",  "label": "No", "key": "B"}
  ]
}
```

```json
{"type":"approval_response","approval_id":"apr_7f3c...","option_id":"allow","source":"button"}
{"type":"approval_result","approval_id":"apr_7f3c...","accepted":true,"reason":"ok"}
```

Reglas:

- El gateway rechaza un `approval_id` caducado, ya resuelto o de otro agente.
- `source` puede ser `button` o `voice`; si es voz, incluye `transcript` y el usuario debe confirmar antes de enviar.
- Un `approval_response` duplicado devuelve el mismo resultado (idempotencia), no una segunda aprobación.

### 5.4. Audio y transcripción

```json
{"type":"audio_start","agent_id":"claude-code","sample_rate":16000,"format":"s16le","channels":1}
{"type":"audio_end","seq":42,"duration_ms":3200}
{"type":"transcript","text":"ejecuta los tests de autenticación","language":"es","confidence":0.93,"final":true}
{"type":"inject_text","agent_id":"claude-code","text":"ejecuta los tests de autenticación","confirm":true}
```

### 5.5. Mantenimiento

- `ping`/`pong` cada 10 s; si fallan 3, el dispositivo pasa a `OFFLINE`.
- Reconexión con *backoff* 1–30 s y *jitter*.
- `error` con `code`, `message`, `retryable`.
- Límite de frame: 8 KB para JSON, 4 KB para audio.
- `seq` monotónico por sesión; el dispositivo descarta estados viejos.

---

## 6. Presupuesto de latencia

| Etapa | Objetivo | Nota |
|---|---|---|
| Captura I2S + framing | 20–40 ms | buffers DMA de 20 ms |
| Envío WiFi LAN | 10–40 ms | 2,4 GHz; mantener WiFi power save off |
| VAD / endpointing | 200–400 ms | Silero VAD; soltar PTT ya marca el final |
| STT | 150–800 ms | GPU vs CPU; modelo caliente |
| Render de transcripción | 20 ms | LVGL |
| Confirmación humana | — | fuera del presupuesto |
| Inyección en el agente | 20–80 ms | API/hook o PTY |
| **Total tras soltar PTT** | **p95 < 1,5 s** | sin contar la confirmación |

Para aprobaciones, el objetivo es **< 150 ms de ida y vuelta en LAN**; por eso el control va separado del audio.

---

## 7. Cómo integrar cada agente (matriz de decisión)

| Agente | Estado | Integración | Riesgo |
|---|---|---|---|
| Claude Code | Soportado | Hook HTTP `PermissionRequest` + `Notification`/`Stop`; OTel para coste si está disponible | Bajo |
| OpenCode | Soportado | `opencode serve` + SSE + endpoint de permisos | Bajo |
| Codex | Soportado con reservas | `exec --json` o app-server; fijar versión | Medio |
| Antigravity | A verificar | API/IDE; si no, PTY | Alto |
| Otros CLIs | Fallback | PTY + `pyte` + patrones configurables | Alto |

**No vendas "agnóstico" como "funciona con cualquier cosa sin configuración".** Véndelo como "adaptadores para los agentes principales y un modo PTY para el resto". Es más honesto y más fácil de mantener.

---

## 8. Decisiones que hay que tomar antes de escribir código

1. **Windows nativo o WSL** para el gateway. Afecta a PTY, paths, hooks y servicio.
2. **Suscripción o API key** para cada agente. Cambia el significado del coste y la viabilidad del proxy.
3. **Agentes prioritarios.** Recomiendo Claude Code + OpenCode para la v1; Codex después.
4. **3,5" o 4,0".** Recomiendo 3,5" SPI para la v1.
5. **D-pad o stick.** Recomiendo D-pad de 5 pulsadores; el stick añade calibración y deriva.
6. **¿Voz con confirmación?** Recomiendo sí: preview + `[A]` para enviar. Nunca inyección automática.
7. **¿PCB propia o devkit + protoboard?** Para la v1, devkit y cableado; la PCB llega cuando el pinout esté validado.
8. **Idiomas de STT.** Español/catalán/inglés; define el orden de prioridad y el modelo.
9. **Impresión 3D:** PETG para la carcasa, PLA para prototipos; inserts M2,5; tolerancia 0,2 mm.

---

## 9. Hoja de ruta revisada (con criterios de salida)

| Fase | Duración | Entregable | Criterio de salida |
|---|---|---|---|
| **0. Gateway + protocolo** | 1–2 semanas | FastAPI + WebSocket, estado, aprobaciones, agente falso, panel web | Aprobar/denegar desde el navegador; p95 < 150 ms; 24 h sin fugas |
| **0.5. Adaptadores + STT** | 1–2 semanas | Claude Code hook, OpenCode server, coste, faster-whisper | Aprobar un `Bash` real desde el panel; WER < 10 % en frases de prueba |
| **1. Banco de pruebas** | 1 semana (pedidos) | DevKit, LCD, INMP441, MAX98357A, botones, fuente | Pantalla, mic y altavoz funcionando en protoboard |
| **2. Firmware UI + WS** | 2–3 semanas | LVGL, tarjetas, modal, reconexión, OTA, portal WiFi | 20–30 fps en refresco parcial; reconexión < 5 s; OTA con rollback |
| **3. Audio y voz** | 1–2 semanas | PTT, VAD, streaming, preview, feedback | p95 < 1,5 s; medio duplex sin eco; 100 dictados sin bloqueo |
| **4. Mecánica** | 2–3 semanas | Carcasa, bisagra, cable, botones | 10.000 ciclos; ángulo estable; sin daño de cable |
| **5. Integración y fiabilidad** | 1–2 semanas | Ensayos, auditoría, seguridad, EMC/potencia | 72 h de soak; 1.000 aprobaciones; WiFi caído/reconectado |
| **6. Pulido y documentación** | 1 semana | Guía de montaje, BOM final, firmware 1.0 | Reproducible por otra persona |

Total estimado: **10–14 semanas** a tiempo parcial, sin contar esperas de proveedores.

---

## 10. Quick wins (próximos 14 días)

1. **Gateway con agente falso** y panel web: valida estado, aprobaciones, `approval_id` y reconexión sin hardware.
2. **Esquema JSON v1** y pruebas con `websocat`; publica el esquema en el repo.
3. **Medir STT en tu PC** con 20 comandos reales (español/catalán/inglés) y tres modelos; decide GPU/CPU con datos.
4. **Probar el hook `PermissionRequest` de Claude Code** contra un endpoint local; mide cuánto puede esperar sin bloquear la TUI.
5. **Pedir el kit de banco** (devkit, 3,5" SPI, INMP441, MAX98357A, botones, fuente) antes de la carcasa.
6. **Prototipo de bisagra con cartón/impresión rápida** y un cable de 10 hilos: mide radio, holgura y par antes de diseñar la tapa.
7. **Definir la política de riesgo** (`normal`/`alto`/`crítico`) y el *hold-to-confirm* desde el primer prototipo, no después.

---

## 11. Conclusión

La especificación describe un producto deseable y factible, con un BOM razonable y una buena intuición de uso. Lo que hay que cambiar no es la idea, sino **la confianza depositada en el PTY y en el botón único**. Con adaptadores nativos, aprobaciones identificadas, autenticación y un presupuesto de latencia honesto, batonAI pasa de "prototipo que funciona en la demo" a "cacharro que puedes dejar en el escritorio sin miedo".

Si tuviera que resumirlo en una frase: **haz que el dispositivo sea un mando remoto de los permisos nativos del agente, no un teclado que adivina lo que hay en la terminal.**

---

### Referencias consultadas

- Claude Code — Hooks reference, `PermissionRequest`, `Notification`, `Stop`: <https://code.claude.com/docs/en/hooks>
- OpenCode — Server API, SSE `/event`, `POST /session/:id/permissions/:permissionID`: <https://opencode.ai/docs/server/>
- OpenCode — Permissions: <https://opencode.ai/docs/permissions/>
- ESP-IDF — External RAM y restricciones de PSRAM en ESP32-S3: <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/external-ram.html>
- faster-whisper: <https://github.com/SYSTRAN/faster-whisper>
- LVGL — display buffers y `esp_lvgl_port`: <https://docs.lvgl.io/>

> Nota: las URLs se consultaron en noviembre de 2026. Las APIs de los agentes cambian con frecuencia; fija versiones y prueba los adaptadores en CI.
