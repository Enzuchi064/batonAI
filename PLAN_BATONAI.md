# batonAI — Plan de proyecto (v0.1)

## 1. La idea en una frase

Un panel físico de sobremesa, siempre encendido, que te dice de un vistazo qué agentes están trabajando, cuáles te necesitan y te permite resolver la interrupción o dictar una instrucción sin cambiar de ventana.

## 2. Contexto

- **Tipo:** proyecto personal. Si funciona y alguien se interesa, se puede vender alguna unidad.
- **Usuario:** tú, trabajando en el PC con 2–3 agentes en paralelo.
- **Uso principal:** orquestar y vigilar agentes mientras haces otras cosas.
- **No es:** un segundo monitor, una consola de logs ni un sustituto del PC.

## 3. Principio rector: gestionar atención, no mostrar datos

El dispositivo compite por tu atención. Debe ganarla solo cuando importa.

- **Silencio por defecto.** Si todos los agentes trabajan, la pantalla está tranquila.
- **Una alerta = una decisión que solo puedes tomar tú.** Nada de notificaciones de progreso.
- **Un vistazo = estado. Una acción = resolver.** Si hace falta navegar tres menús, el diseño ha fallado.
- **Agrupa y prioriza.** Si tres agentes esperan, primero el bloqueante, no el último que llegó.
- **No obliga a mirar.** Si no hay nada urgente, el cacharro puede estar apagado visualmente.

## 4. Qué es "orquestador" aquí

Conviene separar tres niveles, porque el software crece mucho entre uno y otro:

| Nivel | Qué hace | ¿MVP? |
|---|---|---|
| **1. Panel de control** | Ver estado, aprobar/denegar, cambiar de agente, dictar | **Sí** |
| **2. Despachador** | Asignar tareas, colas, dependencias entre agentes | Después |
| **3. Orquestador autónomo** | Descomponer objetivos, rutear trabajo, supervisar | Mucho después |

batonAI es la **interfaz física** del orquestador; el orquestador vive en el PC. Para la v1, nivel 1 bien hecho. El nivel 2 se diseña cuando el nivel 1 se use a diario.

## 5. Alcance del MVP (v0)

**Incluye:**

- 2–3 agentes registrados (Claude Code y OpenCode primero).
- Estado por agente: `RUNNING`, `WAITING_INPUT`, `DONE`, `ERROR`, `OFFLINE`.
- Tarea actual, última línea de log y coste/tokens si el agente ya los expone.
- Cola de atención: quién necesita input y desde cuándo.
- Aprobar/denegar con contexto: comando, `cwd`, riesgo y caducidad.
- Cambiar de agente con D-pad.
- PTT con transcripción y **preview antes de enviar**.
- Aviso por LED/buzzer cuando un agente se bloquea.
- Reconexión y estado "gateway caído".

**No incluye (v1):**

- Proxy de costes propio.
- Pantalla de 4,0", táctil o 60 fps.
- Altavoz/TTS.
- Batería, PCB propia, carcasa clamshell final.
- Más de un PC o más de un usuario.
- Orquestación de tareas (nivel 2).
- OTA, certificación, packaging.

## 5.1. Flujo de pantallas (MVP)

### Dashboard

- 2–3 tarjetas, una por agente.
- Por tarjeta: nombre, modelo, estado, tarea actual, tiempo en estado, última línea y coste si el agente lo expone.
- Orden: `WAITING_INPUT` primero, luego `ERROR`, `RUNNING`, `IDLE`.
- Un contador global: "2 te necesitan".
- Si no hay nada urgente, modo ambiente: sin animaciones ni ruido.

### Detalle de agente

- Tarea actual, últimos 10–15 logs, coste/tokens y `cwd`.
- Acciones: dictar tarea (PTT), volver, interrumpir (mantener `[B]`).
- Si el agente está `RUNNING`, el dictado se encola y la pantalla avisa: "se enviará al terminar". Ofrecer "enviar ahora" solo si el agente lo permite.

### Modal de intervención

No es lo mismo un permiso que una pregunta:

- **Permiso:** comando, `cwd`, riesgo y opciones (permitir / denegar / permitir siempre…).
- **Pregunta:** texto de la pregunta y opciones; si ninguna encaja, PTT para responder libre.
- Las opciones son **dinámicas (2–4)**, no un `[y/N]` fijo:
  - D-pad para seleccionar, `[A]` para confirmar.
  - Si solo hay dos, `[A]`/`[B]` directos.
  - `[B]` siempre cancela o cierra; nunca aprueba.
- `approval_id`, caducidad y resultado visible.
- Riesgo alto: mantener `[A]` para confirmar.

### Dictado

- PTT → grabar → transcribir → preview.
- `[A]` envía, `[B]` cancela, PTT otra vez re-graba.
- En v1 no se envía nada sin preview.

### Estados de pantalla

`AMBIENT` (dashboard tranquilo) → `FOCUS` (detalle) → `MODAL` (intervención) → `DICTATION` (preview) → `OFFLINE`.

Una sola modal a la vez. Si hay varias, cola por agente y contador en el dashboard.

## 5.2. Modo observador: el cacharro lee, no posee

Decidido: los agentes siguen viviendo en el PC y en sus terminales. batonAI es un monitor dedicado, no el dueño de las sesiones.

Eso implica un límite técnico importante: **no se puede leer de forma fiable el contenido de una ventana de terminal ajena**. Lo que sí se puede leer es lo que cada agente escribe en su sesión:

| Agente | Fuente de lectura | Qué da |
|---|---|---|
| Claude Code | Transcripciones JSONL en `~/.claude/projects/` + hooks `PermissionRequest`/`Notification`/`Stop` | Mensajes, herramientas, permisos y fin de turno |
| OpenCode | Servidor (`/event` SSE, mensajes de sesión) | Estado, mensajes, permisos y coste |
| Codex | Logs de sesión / app-server según versión | Mensajes y eventos |
| Genérico | Solo PTY si el gateway lo lanzó | Texto de pantalla, sin semántica |

La consecuencia práctica: para ver permisos en tiempo real hace falta instalar un hook o conectar al servidor del agente. Sin eso, el gateway solo puede ver el log cuando el agente lo escribe, no cuando está esperando una tecla.

### Entrada de texto

- **Permisos:** hook/API nativa; es la parte limpia.
- **Dictado:** API del agente si existe (OpenCode); para Claude Code, o se lanza con un wrapper que dé al gateway un canal de entrada, o se acepta automatización de teclado (frágil y roba el foco).
- **Recomendación:** wrapper `baton run claude` que mantiene la terminal pero permite al gateway leer/escribir. El agente sigue en el PC; solo cambia cómo se arranca.

## 5.3. Consecuencia de producto: monitor, no terminal

- El dashboard es lo importante; los logs son secundarios (últimas 3–5 líneas, no scrollback completo).
- La pantalla debe ser legible de un vistazo a 50–70 cm; no un terminal de 80 columnas.
- El dispositivo pasa la mayor parte del tiempo en `AMBIENT`; solo se enciende o alerta cuando hay algo que hacer.
- Si nunca se va a plegar, una base fija inclinada es más robusta y barata que una bisagra. El clamshell tiene sentido si valoras el formato o la portabilidad; si es solo estética, se puede decidir más adelante.

## 6. Hipótesis a validar

| Hipótesis | Cómo se mide | Éxito |
|---|---|---|
| Detectas antes un agente bloqueado | Tiempo desde `WAITING_INPUT` hasta que lo ves | < 30 s, mejor que mirar el PC |
| Reduces cambios de contexto | Nº de veces que cambias de ventana por hora | −50 % |
| El botón físico aporta | Aprobaciones hechas desde el dispositivo vs PC | > 70 % desde el dispositivo |
| El dictado es usable | Dictados enviados sin corregir | > 80 % |
| No es un juguete de fin de semana | Días de uso real tras la novedad | > 14 días |
| Hay interés externo | Personas que lo piden tras verlo | 3–5 personas |

Si fallan las tres primeras, el hardware no merece la pena todavía.

## 7. Fases

| Fase | Tiempo | Qué haces | Criterio para seguir |
|---|---|---|---|
| **A. Gateway + agente falso** | 1 fin de semana | WebSocket, estado, aprobaciones, UI web | Aprobar/denegar desde el navegador |
| **B. Un agente real** | 1 semana | Claude Code u OpenCode, eventos y permisos | Úsalo una semana como pestaña del navegador |
| **C. Prototipo plano** | 1–2 semanas | ESP32 + pantalla + botones + PTT, sin carcasa | Lo dejas en la mesa y lo usas 2 semanas |
| **D. Carcasa y ergonomía** | 2–3 semanas | Clamshell, bisagra, cable, botones | 10.000 ciclos y uso diario |
| **E. Kit vendible (si hay demanda)** | variable | Gateway empaquetado, guía, BOM estable | 3–5 personas lo montan sin ayuda |

El orden importa: **software antes que hardware, y hardware plano antes que carcasa.**

## 8. Presupuesto

Precios en EUR con IVA, comprando en España (Amazon/tiendas) o AliExpress. El rango bajo implica envío lento y riesgo de aduana; el alto, compra local y menos sorpresas. Son estimaciones de noviembre de 2026.

### 8.1. Prototipo de banco (sin carcasa)

| Componente | Bajo | Alto | Nota |
|---|---:|---:|---|
| ESP32-S3 DevKitC-1 N16R8 | 9 | 16 | N16R8 para PSRAM octal |
| LCD 3,5" 480×320 SPI | 13 | 22 | ST7796/ILI9488 |
| INMP441 | 2 | 5 | módulo breakout |
| Buzzer pasivo | 1 | 2 | sustituye altavoz en el MVP |
| Pulsadores + protoboard + cables | 8 | 12 | D-pad, A/B, PTT |
| Fuente 5 V/2 A + cable USB-C | 8 | 12 | |
| **Total** | **41** | **69** | |

Si añades MAX98357A + altavoz, suma 5–10 €. Herramientas aparte.

### 8.2. Unidad final (3,5", clamshell)

| Componente | Bajo | Alto | Nota |
|---|---:|---:|---|
| DevKit N16R8 | 9 | 16 | |
| LCD 3,5" SPI | 13 | 22 | |
| INMP441 | 2 | 5 | |
| MAX98357A + altavoz 8 Ω 1 W | 5 | 10 | |
| D-pad + 2 Choc + keycaps + PTT | 8 | 15 | |
| Bisagra de fricción + eje | 5 | 15 | no escatimar |
| Cable/FPC + conectores + alivio | 4 | 9 | |
| Alimentación (USB-C, interruptor, fusible, caps) | 4 | 8 | |
| Carcasa impresa (filamento y fallos) | 4 | 8 | impresora propia |
| Tornillería, inserts, patas | 3 | 6 | |
| PCB/protoboard y cableado | 4 | 10 | |
| Varios (espuma, termorretráctil, junta mic) | 2 | 4 | |
| **Subtotal** | **63** | **128** | |
| Envío, aduana, impuestos | 10 | 20 | |
| **Total** | **73** | **148** | |

**Objetivo realista:** 90–120 € para una unidad bien hecha, comprando con calma y aceptando algún repuesto.

### 8.3. 3,5" vs 4,0"

| Opción | Precio pantalla | Coste total | Riesgo |
|---|---:|---:|---|
| 3,5" SPI 480×320 | 13–22 € | 73–148 € | Bajo, mucha oferta |
| 4,0" SPI 480×320 | 20–30 € | 80–160 € | Medio, menos módulos |
| 4,0" RGB 480×800 | 25–40 € + driver | 95–180 € | Alto: 16+ pines, PSRAM, carcasa |

Para la v1, 3,5" SPI. El 4,0" no aporta suficiente para justificar el riesgo.

### 8.4. Lote pequeño (5–10 unidades)

| Concepto | Kit | Ensamblado |
|---|---:|---:|
| Componentes (descuento 10–20 %) | 55–95 | 55–95 |
| Carcasa impresa | 4–8 | 4–8 |
| PCB propia (10 uds.) | 8–15 | 8–15 |
| Montaje (1,5–3 h × 15–20 €/h) | — | 22–60 |
| Packaging y documentación | 3–6 | 3–6 |
| **Coste por unidad** | **70–124** | **92–184** |
| **Precio de venta sugerido** | **110–160** | **180–250** |

A 5 unidades, el margen es fino y el soporte se come la diferencia. Si se vende, que sea kit y con 2–3 agentes soportados, no "todos".

### 8.5. Costes que no están en la BOM

- **Herramientas:** soldador 25–60 €, multímetro 20–40 €, calibre 15–25 €, analizador lógico 10–20 €. Impresora 3D 200–400 € (o makerspace).
- **Tiempo:** 20–40 h la primera unidad; 5–10 h las siguientes. A 15 €/h, la primera unidad "cuesta" 300–600 € en tiempo.
- **Repuestos:** compra 2 pantallas y 2 micrófonos; un fallo no debe parar el proyecto un mes.
- **Certificación:** si algún día vendes como producto, CE/RED y EMC pueden ser 1.500–4.000 €. No tiene sentido a 5 unidades.
- **Soporte:** cada actualización de Claude Code/OpenCode puede romper un adaptador. Es coste recurrente.

### 8.6. Dónde se va el dinero

- Pantalla: 20–25 %.
- Mecánica (bisagra, carcasa, tornillería): 15–20 %.
- Microcontrolador: 12–15 %.
- Conectores, alimentación y cableado: 10–15 %.
- Audio: 8–12 %.
- Envío e impuestos: 10–15 %.

Si hay que recortar: 3,5" en vez de 4,0", buzzer en vez de altavoz, pulsadores táctiles en el prototipo y Choc solo en la versión final. Si no hay que recortar: bisagra, USB-C y protecciones de alimentación.

## 9. Riesgos

| Riesgo | Nivel | Mitigación |
|---|---|---|
| El dispositivo no aporta frente a una pestaña del navegador | Alto | Fase A/B antes de comprar hardware; medir uso real |
| Aprobar por accidente un comando destructivo | Alto | `approval_id`, contexto, hold-to-confirm, timeout |
| Depender de scraping de PTY | Alto | Adaptadores nativos; PTY solo como fallback |
| La carcasa/bisagra queda frágil | Medio | Prototipo plano primero; bisagra de fricción con canal |
| Vender y no poder dar soporte | Medio | Vender kit, limitar agentes soportados, documentar |
| Certificación/CE si se vende | Bajo (ahora) | Posponer; no prometer producto terminado |

## 10. Decisiones abiertas

1. **Profundidad de orquestación:** cerrado en nivel 1 (panel de control). Nivel 2 más adelante.
2. **Primer agente:** Claude Code u OpenCode.
3. **Pantalla:** ¿logs (3,5") o solo estado (2,4")?
4. **Aviso:** LED, buzzer, háptica o combinación.
5. **Venta:** ¿kit DIY o ensamblado? (recomendado: kit, y solo si 3–5 personas lo piden).
6. **Gateway:** Windows nativo o WSL.
7. **Formato:** clamshell plegable o base fija inclinada.
8. **Entrada de dictado:** wrapper `baton run` o automatización de teclado.

## 11. Próximo hito

**Fase A:** gateway con agente falso y UI web. Sin hardware.

Al terminarla sabrás si el flujo "ver estado → aprobar → dictar" es cómodo. Si no lo es en una pestaña del navegador, tampoco lo será en una pantalla de 3,5".
