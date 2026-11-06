# Diseño de software — batonAI (v0.1)

**Estado:** Fase A implementada y ejecutable.
**Fecha:** noviembre de 2026.
**Documentos relacionados:** `PLAN_BATONAI.md`, `REVISION_TECNICA_BATONAI.md`, `LISTA_COMPRA_BATONAI.md`, `DISENO_FIRMWARE_BATONAI.md`.

Este documento describe el software de la Fase A: un gateway local que mantiene el
estado de los agentes, arbitra aprobaciones con identidad y sirve un panel web que
se comporta como el dispositivo. **No hay hardware, ni agentes reales, ni STT
todavía**; esos límites están explicados en la sección 13.

---

## 1. Decisiones cerradas

| Decisión | Valor | Motivo |
|---|---|---|
| Stack del gateway | Python 3.11+ con FastAPI, Pydantic v2, uvicorn | Encaja con `faster-whisper` en la fase 0.5 y con los hooks/SSE de los agentes |
| Entorno | Windows nativo | Fase A no necesita PTY; se evita la fricción de WSL con rutas y hooks |
| Primer agente | Agente falso (`FakeAgentAdapter`) | Valida el flujo sin credenciales ni dependencias externas |
| Transporte | WebSocket JSON en `/ws/control`, binario en `/ws/audio` | El control nunca espera al audio |
| Identidad de aprobación | `approval_id` + caducidad + resultado idempotente | Una pulsación tardía no puede aprobar otra cosa |
| Autenticación | Emparejamiento TOTP con QR + token por dispositivo (hash SHA-256 en BD) | Cierra el "aprobar sin autenticar" de la especificación original |
| Administración | Endpoints `/api/*` solo desde loopback | El panel no se expone a la LAN |
| Persistencia | SQLite (`gateway/var/baton.db`) para auditoría y dispositivos | El estado es efímero; la auditoría sobrevive |
| UI de referencia | Panel web con la misma máquina de estados y el mismo protocolo | Si el flujo no es cómodo en el navegador, no lo será en 3,5" |

Lo que sigue abierto (no bloquea la Fase A): Windows nativo vs WSL para los
adaptadores reales, primer agente real (Claude Code u OpenCode), TLS con
certificado fijado y política de retención de la auditoría.

---

## 2. Principios

1. **El gateway es la única fuente de verdad.** El dispositivo renderiza estado
   y captura input; nunca decide si una aprobación es válida.
2. **El dispositivo propone, el gateway decide, el agente confirma.** El botón
   físico no escribe en una terminal: responde a una petición con identidad.
3. **Aprobar es un acto con ceremonia proporcional al riesgo.** Riesgo normal:
   una pulsación. Riesgo alto: mantener 1,5 s. Crítico: 2,5 s.
4. **Adaptadores, no scraping.** Cada agente habla su idioma nativo (hook HTTP,
   SSE, JSON-RPC); el PTY queda como último recurso y nunca como base.
5. **Fallo cerrado en lo que aprueba, fallo abierto en lo que bloquea.** Si el
   gateway no está, el prompt nativo del agente sigue en el PC; nunca se
   auto-aprueba para "seguir adelante".
6. **Silencio por defecto.** La UI solo reclama atención cuando hay una decisión
   que únicamente puede tomar el usuario.

---

## 3. Componentes

```text
┌──────────────────────────────┐        ┌──────────────────────────────┐
│ Panel web (Fase A)           │        │ Dispositivo ESP32 (Fase C)   │
│ mismo protocolo que el mando │        │ LVGL + D-pad + PTT           │
└──────────────┬───────────────┘        └──────────────┬───────────────┘
               │  WSS /ws/control (JSON)               │
               │  WSS /ws/audio   (PCM s16le 16 kHz)   │
               ▼                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Gateway local (FastAPI)                                              │
│                                                                      │
│  DeviceHub ───── PairingManager ───── AuditLog (SQLite)              │
│  conexiones      código + tokens       devices / approvals / events  │
│                                                                      │
│  AgentSupervisor                                                     │
│    ├── StateStore          estado validado y ordenado                │
│    ├── ApprovalBroker      approval_id, riesgo, caducidad, idempotencia│
│    └── adaptadores                                                   │
│          └── FakeAgentAdapter        (Fase A)                        │
│          ├── ClaudeCodeAdapter       (fase 0.5, hook HTTP)           │
│          └── OpenCodeAdapter         (fase 0.5, SSE + permissions)   │
│                                                                      │
│  STTService (fase 0.5)     VAD + faster-whisper, modelo caliente     │
└──────────────────────────────────────────────────────────────────────┘
```

Flujo de responsabilidades:

- **Adaptador**: traduce un agente a eventos (`status`, `log`, `approval`,
  `usage`, `error`). No escribe estado ni habla con el dispositivo.
- **Supervisor**: valida transiciones, crea aprobaciones, publica estado,
  resuelve y avisa al adaptador. Es el único que escribe en `StateStore`.
- **Broker**: guarda la verdad de cada aprobación y sus reglas de caducidad,
  idempotencia y obsolescencia.
- **Hub**: entrega mensajes a los dispositivos conectados. No conoce el dominio.
- **Auditoría**: registra lo que hay que poder responder después: quién aprobó
  qué, cuándo y con qué resultado.

---

## 4. Repositorio

```text
batonAI/
├── PLAN_BATONAI.md
├── REVISION_TECNICA_BATONAI.md
├── LISTA_COMPRA_BATONAI.md
├── DISENO_SOFTWARE_BATONAI.md        ← este documento
└── gateway/
    ├── pyproject.toml
    ├── README.md
    ├── baton/
    │   ├── __main__.py               CLI: serve, pair
    │   ├── api.py                    rutas HTTP y WebSocket
    │   ├── services.py               ensamblaje y mensajes del dispositivo
    │   ├── config.py                 Settings (BATON_*)
    │   ├── protocol.py               modelos Pydantic del protocolo v1
    │   ├── state.py                  AgentStatus, StateStore, transiciones
    │   ├── broker.py                 ApprovalBroker y Resolution
    │   ├── risk.py                   clasificador de riesgo + hold_ms
    │   ├── audit.py                  SQLite: devices, approvals, events
    │   ├── pairing.py                código de 6 dígitos y tokens
    │   ├── hub.py                    DeviceHub y DeviceConnection
    │   ├── discovery.py              detección de OpenCode y sincronización
    │   ├── local_agents.py           Claude Code, Codex, Gemini, Antigravity, Cursor, Copilot
    │   ├── limits.py                 agregación y selección de límites
    │   ├── opencode_usage.py         límites reales de OpenCode
    │   ├── codex_usage.py            límites reales de Codex
    │   ├── claude_usage.py           límites reales de Claude Code
    │   ├── adapters/
    │   │   ├── base.py               AgentAdapter, AgentEvent
    │   │   ├── fake.py               agente de demostración
    │   │   ├── opencode.py           permisos, prompts e interrupción de OpenCode
    │   │   └── supervisor.py         orquestación
    │   └── static/                   panel web (HTML/CSS/JS sin build)
    ├── tests/                        136 pruebas
    └── var/                          base de datos (no versionada)
```

Sin bundler, sin framework de UI y sin base de datos externa: el panel se sirve
tal cual y la única dependencia de ejecución es Python.

---

## 5. Modelo de dominio

### 5.1. Agente y estados

`AgentStatus`: `IDLE`, `RUNNING`, `WAITING_INPUT`, `DONE`, `ERROR`, `OFFLINE`.

| Estado | Significado | Sale hacia |
|---|---|---|
| `IDLE` | Vivo, sin tarea | `RUNNING`, `WAITING_INPUT`, `ERROR`, `OFFLINE` |
| `RUNNING` | Procesando o ejecutando herramientas | `WAITING_INPUT`, `IDLE`, `DONE`, `ERROR`, `OFFLINE` |
| `WAITING_INPUT` | Bloqueado esperando al usuario | `RUNNING`, `IDLE`, `ERROR`, `OFFLINE` |
| `DONE` | Tarea terminada, proceso vivo | `IDLE`, `RUNNING`, `OFFLINE` |
| `ERROR` | Fallo de ejecución | `IDLE`, `RUNNING`, `OFFLINE` |
| `OFFLINE` | Sin heartbeat o adaptador caído | `IDLE`, `RUNNING`, `WAITING_INPUT`, `DONE`, `ERROR` |

Reglas implementadas en `state.py`:

- Una transición no permitida lanza `InvalidTransition`; el supervisor lo
  registra en auditoría y **no** cambia el estado.
- Repetir el mismo estado no reinicia `since` (el "tiempo en estado" no se
  reinicia con cada log).
- Salir de `WAITING_INPUT` limpia `approval_id`, `prompt` y `risk`: una espera
  sin petición asociada es un estado mentiroso.
- `clear_approval` sin estado destino degrada a `IDLE`, nunca deja
  `WAITING_INPUT` huérfano.
- `DONE` no cierra el proceso: es el fin de un turno, no del agente.

Campos por agente: `id`, `name`, `provider`, `model`, `status`, `since`,
`last_event_at`, `cwd`, `task`, `log_tail` (5 líneas por defecto), `cost_turn`,
`cost_session`, `tokens_session`, `approval_id`, `prompt`, `risk`.

Orden del dashboard: `WAITING_INPUT` → `ERROR` → `RUNNING` → `DONE` → `IDLE` →
`OFFLINE`; dentro de cada estado, el más antiguo primero.

### 5.2. Aprobaciones

Estados: `pending` → `accepted` | `rejected` | `expired` | `stale`.

| Situación | Resultado | ¿Aprieta el agente? |
|---|---|---|
| El usuario permite | `accepted` | Sí, con la opción `allow` |
| El usuario deniega | `rejected` | Sí, con la opción `deny` |
| Pasa `expires_at` | `expired` | No: se avisa al adaptador para que deje el prompt nativo |
| El agente cambia de estado o pide otra cosa | `stale` | No |
| Llega un `approval_id` desconocido | `unknown` | No, y se devuelve error |
| La opción no existe en esa petición | `invalid_option` | No, la petición sigue pendiente |
| Se responde dos veces | mismo resultado, `duplicate: true` | No se ejecuta dos veces |

Detalles de seguridad:

- El `approval_id` lo aporta el adaptador (id nativo del agente si existe).
- El broker rechaza ids duplicados y peticiones nuevas del mismo agente
  invalidan la anterior (`stale`).
- La caducidad se evalúa tanto al resolver como en un bucle cada 0,5 s.
- El dispositivo no calcula el tiempo de espera: recibe `hold_ms` ya decidido.

### 5.3. Riesgo

`Risk`: `low`, `normal`, `high`, `critical`. El clasificador (`risk.py`) es una
lista de patrones, no un analizador semántico:

- **Crítico:** `rm -rf /`, `mkfs`, `dd of=/dev/*`, `diskpart`, `format C:`,
  apagado del equipo, fork bomb, `DROP DATABASE`.
- **Alto:** `rm -rf`, `git push --force`, `git reset --hard`, `git clean -fdx`,
  `sudo`, `chmod 777`, `curl | sh`, `npm publish`, dependencias desde URL,
  `DROP TABLE`, `del /f`, cambios de registro/ACL en Windows.
- **Bajo:** lectura evidente (`ls`, `cat`, `git status`, `rg`, `git diff`…).
- **Normal:** todo lo demás. Nunca se baja a `low` si algo ha encendido una
  señal de riesgo.

Un patrón de lectura no puede rebajar el riesgo: `git status && rm -rf build`
es `high`. `hold_ms`: 0 / 0 / 1500 / 2500 ms.

**Límite conocido:** los patrones no entienden de contexto. Su función es subir
la ceremonia, no sustituir el juicio del usuario ni la política del agente.

---

## 6. Protocolo v1

### 6.1. Transporte y handshake

- `/ws/control`: JSON de texto. Máximo 8 KB por mensaje.
- `/ws/audio`: binario PCM `s16le`, mono, 16 kHz, más mensajes JSON de ciclo de
  vida (`audio_start`, `audio_end`).
- El primer mensaje de cualquier socket es `hello`. Si no llega en 10 s, se
  cierra con 4408. Token inválido: 4401. Versión distinta: 4426.

```json
{"type":"hello","proto":1,"device_id":"baton-web-<id>","fw":"0.1.0","token":"<token>"}
{"type":"welcome","proto":1,"session_id":"…","server_time":"2026-11-04T10:00:00.000Z",
 "device_id":"baton-web","config":{"heartbeat_s":10,"approval_timeout_s":60,"hidden_agents":[],"pinned_agents":[]}}
```

### 6.2. Mensajes

Entrantes:

| Tipo | Campos | Notas |
|---|---|---|
| `hello` | `proto`, `device_id`, `fw`, `token` | Obligatorio y primero |
| `approval_response` | `approval_id`, `option_id`, `source`, `transcript?` | `source`: `button` o `voice` |
| `interrupt` | `agent_id` | Acción separada de "denegar" |
| `inject_text` | `agent_id`, `text`, `confirm` | Sin `confirm: true` se rechaza |
| `ping` | `seq` | Respuesta `pong` con el mismo `seq` |
| `audio_start` / `audio_end` | `agent_id`, `seq`, `duration_ms` | Solo por `/ws/audio` |

Salientes:

| Tipo | Contenido |
|---|---|
| `welcome` | Sesión, hora del servidor, configuración |
| `state` | `seq`, `ts`, `system`, `agents[]` |
| `visibility` | `hidden_agents[]`, `ts` (política de visibilidad) |
| `pinned` | `pinned_agents[]`, `ts` (agentes fijados, máximo 2) |
| `approval_request` | `approval_id`, agente, tipo, título, comando completo, `cwd`, riesgo, `expires_at`, opciones, `hold_ms`, motivos |
| `approval_result` | `approval_id`, `status`, `accepted`, `option_id`, `reason`, `duplicate` |
| `ack` | `ref`, `ok`, `detail` |
| `error` | `code`, `message`, `retryable` |
| `pong` | `seq` |
| `transcript` | `text`, `language`, `confidence`, `final` (reservado para 0.5) |

### 6.3. Ejemplos

```json
{
  "type": "approval_request",
  "approval_id": "apr_44166f5fcd74",
  "agent_id": "claude-code",
  "kind": "bash",
  "title": "Limpiar artefactos de build",
  "command": "rm -rf build/ dist/ .cache/",
  "cwd": "C:\\dev\\baton-demo",
  "risk": "high",
  "expires_at": "2026-11-04T19:35:30.290Z",
  "options": [
    {"id": "allow", "label": "Permitir", "key": "A"},
    {"id": "deny", "label": "No", "key": "B"}
  ],
  "hold_ms": 1500,
  "reasons": ["borrado recursivo"]
}
```

```json
{"type":"approval_response","approval_id":"apr_44166f5fcd74","option_id":"allow","source":"button"}
{"type":"approval_result","approval_id":"apr_44166f5fcd74","status":"accepted","accepted":true,"option_id":"allow","reason":"ok"}
{"type":"ack","ref":"approval_response","ok":true,"detail":"ok"}
```

### 6.4. Reglas

- `seq` es monótono por sesión de gateway; el dispositivo descarta estados con
  `seq` menor.
- Los estados se publican con coalescencia de 80 ms para no saturar de frames.
- `approval_result` se difunde a todos los dispositivos; `ack` solo al que
  respondió.
- Idempotencia: repetir una respuesta devuelve `duplicate: true`, no una segunda
  aprobación.
- Un `inject_text` sin `confirm: true` devuelve `confirmation_required`.
- La política de visibilidad viaja en `welcome.config.hidden_agents` y se
  actualiza con `visibility`; el dispositivo recibe todos los agentes y filtra
  localmente. El gateway no deja de conocer ni de auditar a los ocultos.
- Cualquier campo desconocido invalida el mensaje (`extra="forbid"`): un JSON
  hostil no puede colar campos por accidente.

### 6.5. Audio

Formato previsto: `s16le`, mono, 16 kHz. El panel y el firmware envían
`audio_start` al empezar a grabar y `audio_end` al soltar PTT. En Fase A el
gateway acepta los frames y responde `stt_not_configured` al cerrar la
utterance: preferimos un error explícito a inventar una transcripción.

---

## 7. Seguridad

Implementado en Fase A:

- **Emparejamiento (simulador):** código de 6 dígitos emitido por el gateway,
  rotación cada 10 minutos, token aleatorio de 32 bytes. En la BD solo se guarda
  SHA-256. El hardware usa el flujo TOTP descrito en
  [`DISENO_EMPAREJAMIENTO_TOTP.md`](DISENO_EMPAREJAMIENTO_TOTP.md): QR
  `otpauth` en el dispositivo, código verificado por el dispositivo y un solo PC
  emparejado a la vez.
- **Sesión:** sin token válido no hay WebSocket; el hub rechaza el handshake y
  cierra con 4401.
- **Acciones con identidad:** el broker comprueba que el `approval_id` existe,
  está pendiente y pertenece a ese agente.
- **Idempotencia:** un doble toque no ejecuta dos veces.
- **Administración local:** `/api/dev/*`, `/api/state`, `/api/audit` y
  `/api/devices` solo responden a loopback.
- **Auditoría:** tabla `approvals` con dispositivo, opción, origen y resultado;
  tabla `events` para ciclo de vida.
- **Secretos:** el dispositivo nunca ve API keys ni el contenido de los prompts
  del agente; solo el comando a aprobar y el texto que él mismo dictó.
- **Panel:** el token se guarda en `localStorage`; si el gateway lo invalida, el
  panel vuelve a emparejarse.

Pendiente antes de usar en una red no confiable:

- TLS con certificado autofirmado y *fingerprint* fijado en el dispositivo.
- Rate limiting por dispositivo y por acción.
- Ventana anti-replay basada en `seq`/`ts`.
- Interruptor físico de mute del micrófono y LED de grabación.
- Rotación/revocación de tokens desde la UI (el endpoint de revocación existe).
- Servicio de Windows (NSSM o Tarea Programada) con bandeja y logs.

> El panel de Fase A escucha en `127.0.0.1` por defecto. `--host 0.0.0.0`
> existe para probar con el dispositivo en la LAN y debe usarse solo en una red
> de confianza: la autenticación protege las acciones, pero no cifra el tráfico.

---

## 8. Flujos

### 8.1. Aprobar un permiso

```text
Adaptador          Supervisor          Broker           Hub          Dispositivo
   │  status WAITING_INPUT │              │               │               │
   ├──────────────────────►│  set_status  │               │  state        │
   │                       ├─────────────►│               ├──────────────►│
   │  approval(id, cmd)    │              │               │               │
   ├──────────────────────►│ create()     │               │               │
   │                       ├─────────────►│               │               │
   │                       │              │  approval_request             │
   │                       ├──────────────┼──────────────►├──────────────►│
   │                       │              │               │   usuario     │
   │                       │              │◄──────────────┼───────────────┤
   │                       │  resolve()   │  respuesta    │               │
   │                       │◄─────────────┤               │               │
   │  respond(allow)       │              │               │ approval_result│
   │◄──────────────────────┤              ├──────────────►├──────────────►│
   │  status RUNNING       │  state       │               │               │
   ├──────────────────────►├──────────────┼──────────────►├──────────────►│
```

El orden importa: se actualiza el estado local antes de avisar al adaptador,
para que su siguiente evento no compita con una aprobación ya resuelta.

### 8.2. Caducidad

Cada 0,5 s el supervisor llama a `broker.expire_due()`. Las peticiones vencidas
pasan a `expired`, se limpian del estado, se difunde `approval_result` y se
llama a `adapter.notify_expired()`. El adaptador **deja el prompt nativo en el
PC**; nunca aprueba para desbloquearse.

### 8.3. Obsolescencia

Si el agente sale de `WAITING_INPUT` sin respuesta (terminó, falló o pidió otra
cosa), el supervisor marca las aprobaciones pendientes como `stale`. La pantalla
recibe el resultado y deja de mostrar el modal.

### 8.4. Reconexión

El dispositivo reconecta con backoff 0,8–30 s y jitter. Al conectar recibe
`welcome`, un `state` completo y **todas las aprobaciones pendientes** con su
petición completa. Esa re-sincronización evita el peor estado posible: un
dispositivo que muestra `WAITING_INPUT` sin el modal que lo explica. El hub
reemplaza la conexión anterior del mismo `device_id` y cierra la vieja con 4409.
Si el gateway cae, el panel muestra "Gateway desconectado" y deja de presentar
la última telemetría como actual.

### 8.5. Dictado (diseñado, no implementado)

1. PTT → `audio_start` → frames PCM por `/ws/audio`.
2. Soltar → `audio_end`; VAD confirma el final.
3. STT (faster-whisper caliente) → `transcript` con `final: true`.
4. El dispositivo muestra el texto; `[A]` envía, `[B]` cancela, PTT regraba.
5. `inject_text` con `confirm: true` al adaptador correspondiente.

Nunca se inyecta texto sin preview. Presupuesto: p95 < 1,5 s desde soltar PTT.

---

## 9. Adaptadores

```python
class AgentAdapter(ABC):
    id: str
    name: str
    provider: str
    model: str
    cwd: str

    async def start(self, sink: Sink) -> None: ...
    async def stop(self) -> None: ...
    async def respond(self, approval_id: str, option_id: str) -> None: ...
    async def notify_expired(self, approval_id: str) -> None: ...
    async def send_text(self, text: str) -> None: ...
    async def interrupt(self) -> None: ...
```

`Sink` recibe `AgentEvent(kind, agent_id, payload)`. Tipos: `status`, `log`,
`approval`, `usage`, `error`.

| Agente | Integración prevista | Qué aporta | Estado |
|---|---|---|---|
| Falso | Guion interno | Valida todo el flujo | **Implementado** |
| Claude Code | Hook HTTP `PermissionRequest` + `Notification`/`Stop` | Permiso con `allow`/`deny` sin scraping | Fase 0.5 |
| OpenCode | `opencode serve` + SSE `/event` + `POST /session/:id/permissions/:permissionID` | Estado, permisos, coste | Fase 0.5 |
| Codex | `exec --json` o app-server JSON-RPC | Eventos estructurados | Después |
| Genérico | PTY + `pyte` + patrones | Último recurso | Después |

Reglas del contrato:

- El adaptador **no** escribe en `StateStore` ni habla con el dispositivo.
- Aporta el `approval_id` (nativo si existe) y el comando completo.
- `respond` solo actúa si el id coincide con su petición activa; si no, ignora.
- `notify_expired` no debe aprobar ni denegar: deja el prompt local.
- Un adaptador que lanza una excepción no tumba el gateway: el supervisor la
  registra y marca el agente en `ERROR`.
- Las primitivas asyncio se crean en `start()`, no en `__init__`.

---

## 10. Persistencia y auditoría

SQLite en `gateway/var/baton.db`:

| Tabla | Contenido | Retención prevista |
|---|---|---|
| `devices` | `device_id`, nombre, hash del token, fechas, revocado | Mientras exista el dispositivo |
| `approvals` | Petición completa + resultado + dispositivo + origen | 90 días (configurable) |
| `events` | `device_paired`, `approval_created`, `approval_resolved`, `agent_error`, `text_injected`… | 30 días |
| `agent_visibility` | `agent_id`, `hidden`, `updated_at` | Configuración persistente |
| `agent_pins` | `agent_id`, `pinned_at` | Configuración persistente (máx. 2) |

No se guardan prompts completos ni respuestas del modelo por defecto. La
transcripción de voz se guardará (o su hash) solo si se aprueba explícitamente
en la fase 0.5.

La auditoría crece poco: una fila por aprobación, no por token. El estado en
memoria se reconstruye al arrancar; no se intenta recuperar el estado anterior.

---

## 11. Configuración y operación

```bash
cd gateway
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"

.venv\Scripts\python.exe -m baton serve          # gateway + agente falso
.venv\Scripts\python.exe -m baton serve --no-fake
.venv\Scripts\python.exe -m baton serve --host 0.0.0.0   # solo LAN de confianza
.venv\Scripts\python.exe -m baton pair           # código y salir
.venv\Scripts\python.exe -m pytest -q
```

Variables de entorno (`BATON_*`):

| Variable | Por defecto | Uso |
|---|---|---|
| `HOST` | `127.0.0.1` | Interfaz de escucha |
| `PORT` | `8765` | Puerto |
| `DB_PATH` | `gateway/var/baton.db` | SQLite |
| `APPROVAL_TIMEOUT_S` | `60` | Caducidad de una petición |
| `HEARTBEAT_S` | `10` | Anunciado en `welcome` |
| `MAX_JSON_BYTES` | `8192` | Límite de frame de control |
| `MAX_AUDIO_FRAME_BYTES` | `4096` | Límite de frame de audio |
| `LOG_TAIL` | `5` | Líneas de log por agente |
| `LOG_BUFFER` | `50` | Líneas en memoria |
| `FAKE_AUTOSTART` | `false` | Arranca el agente falso (normalmente solo con `--fake`) |
| `FAKE_AGENTS` | `3` | Número de agentes de demostración (1–3) |
| `FAKE_APPROVALS` | `false` | El agente falso pide permisos por su cuenta (molesto para probar la UI) |
| `DEV_MODE` | `true` | Habilita `/api/dev/*` |
| `OPENCODE_ENABLED` | `true` | Detecta sesiones locales de OpenCode |
| `OPENCODE_URL` | vacío | Fuerza la URL del servidor (si no, se descubre el puerto) |
| `OPENCODE_PASSWORD` | vacío | Fuerza la contraseña (si no, se lee de `service.json`) |
| `OPENCODE_RECENCY_S` | `21600` | Ventana de actividad de las sesiones (6 h) |
| `OPENCODE_MAX_SESSIONS` | `8` | Tope de sesiones publicadas |
| `OPENCODE_POLL_S` | `5` | Intervalo de sondeo |
| `LOCAL_AGENTS_ENABLED` | `true` | Detecta Claude Code, Codex, Gemini, Antigravity, Cursor y Copilot |
| `LOCAL_AGENTS_RECENCY_S` | `43200` | Ventana de actividad de esas sesiones (12 h) |
| `LOCAL_AGENTS_MAX_SESSIONS` | `8` | Tope por fuente |
| `LOCAL_AGENTS_POLL_S` | `10` | Intervalo de sondeo |
| `LOCAL_AGENTS_ACTIVE_S` | `120` | Ventana para considerar una sesión `RUNNING` |
| `LIMITS_ENABLED` | `true` | Activa la lectura de límites de las IAs |
| `LIMITS_POLL_S` | `60` | Refresco de OpenCode y Claude |
| `OPENCODE_LIMITS_ENABLED` | `true` | Lee límites del servidor local de OpenCode |
| `CLAUDE_LIMITS_ENABLED` | `true` | Lee límites de Claude Code |
| `CODEX_USAGE_ENABLED` | `true` | Lee límites del app-server de Codex |
| `CODEX_USAGE_POLL_S` | `120` | Refresco de los límites de Codex |
| `BATON_CODEX_EXE` | vacío | Fuerza la ruta de `codex.exe` |

### 11.1. Detección de agentes

**OpenCode** (`discovery.py`) se descubre con `psutil` (sockets en escucha del
proceso `opencode-cli`), lee la contraseña de
`~/.config/opencode/service.json` y consulta `GET /api/session` con Basic auth.
Las sesiones se publican con id `opencode:<session_id>`; el estado sale de
`time.busy`/`time.idle` y el uso de `cost` y `tokens` (sin contar la caché). Con
la app de escritorio abierta, `drafts.sqlite` aporta las **pestañas abiertas**:
al cerrar una pestaña su agente desaparece en el siguiente sondeo. Sin la app,
se usa la recencia de la API.

**Archivos y SQLite** (`local_agents.py`) cubren al resto:

| Agente | Fuente | Id |
|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | `anthropic:<sesión>` |
| Codex | `~/.codex/sqlite/codex.db`, `state_5.sqlite`, `~/.codex/sessions` | `openai:<hilo>` |
| Gemini CLI | `~/.gemini/tmp/**/chats/session-*.json` | `google:<sesión>` |
| Antigravity | `~/.gemini/antigravity/conversation_summaries.db` | `antigravity:<conversación>` |
| Copilot CLI | `~/.copilot/session-state/**/*.json` (best effort) | `github:<sesión>` |
| Cursor | `state.vscdb` del IDE (composers y chats) | `cursor:<sesión>` |

Las fuentes de archivos son tolerantes a formatos incompletos y se ejecutan en
un hilo para no bloquear el bucle. Filtran por fecha de modificación (12 h por
defecto), limitan a 8 sesiones por fuente y consideran `RUNNING` si la sesión se
actualizó en los últimos 120 s; Antigravity además respeta `not_fully_idle`.
Codex descarta los hilos de ChatGPT y solo publica los locales. Cursor lee
`composer.composerData` y el chat del IDE desde `state.vscdb`; si la base está
bloqueada o no existe, no publica nada.

Todas las fuentes comparten la misma sincronización: actualizan nombre, modelo,
estado y uso, retiran sesiones cerradas y marcan `OFFLINE` si la fuente falla
tres veces seguidas. La **detección** es de solo lectura; las aprobaciones y el
dictado de OpenCode se resuelven por su API (11.3).

Los logos de proveedor están en el panel y en la app: Anthropic, OpenAI,
Google/Gemini, Antigravity, OpenCode, GitHub Copilot y Cursor.

### 11.2. Salida y aviso de finalización

OpenCode expone el último mensaje del asistente en `session_message` (SQLite).
El gateway prefiere su **texto**; si el turno está ejecutando una herramienta,
muestra `→ herramienta: comando/ruta`. Esa salida se guarda como `task` del
agente y como una línea del log, así que aparece en la tarjeta y en el detalle
del panel. Claude Code y Gemini CLI también aportan su último texto.

El panel compara el estado anterior con el nuevo en cada `state`: si un agente
visible pasa de `RUNNING`/`WAITING_INPUT` a `DONE`/`IDLE`, reproduce un ding de
dos tonos con Web Audio. El firmware hará lo mismo por I2S al MAX98357A. Los
agentes ocultos no suenan.

### 11.3. Permisos y PTT

`OpenCodeAdapter` se registra por cada sesión abierta. El descubridor consulta
`GET /api/session/{id}/permission` y convierte la primera petición pendiente en
un `AgentEvent(APPROVAL)`; el supervisor la publica en el panel. La respuesta se
traduce a `POST .../permission/{requestID}/reply`:

- `allow` → `decision: once`
- `deny` → `decision: reject`

Las peticiones se deduplican y no se adelanta la siguiente mientras haya una
pendiente. Si el broker caduca una petición, el prompt nativo de OpenCode sigue
esperando en el PC: no se auto-aprueba ni se auto-deniega.

Para que OpenCode pregunte, el proyecto incluye `opencode.json` con reglas `ask`
para comandos peligrosos (`rm -rf`, force push, sudo, format, shutdown, etc.).
Sin esas reglas, o en otros proyectos, OpenCode puede seguir en `allow` y no
habrá nada que aprobar. Las reglas son ampliables.

El PTT del panel usa la Web Speech API del navegador: transcribe, muestra el
preview y, al pulsar A, envía el texto con
`POST /api/session/{id}/prompt`. El navegador debe tener permiso de micrófono
para `127.0.0.1:8770`; si está bloqueado, el panel avisa y no simula texto. El
hardware usará STT local en el gateway; el socket de audio sigue sin STT.

### 11.4. Agentes fijados

La app de escritorio muestra un **PIN** junto al ojo. Al fijar un agente, el
gateway lo guarda en `agent_pins` y lo publica en `welcome.config.pinned_agents`
y en el mensaje `pinned`. El límite es **dos**: un tercer pin devuelve
`409 pin_limit`; la app lo explica y no lo aplica.

El panel ordena los fijados **arriba del todo**, en el orden en que se fijaron,
con una marca de pin; el resto sigue el orden normal por estado. Si un fijado
está oculto, el ojo manda y no se muestra. Si una sesión desaparece y vuelve,
conserva su pin. El firmware replica este orden y el máximo de dos.

### 11.5. Centro de control

La app de escritorio tiene cuatro vistas:

- **Agentes:** búsqueda, filtros por estado/proveedor, orden, acciones masivas y
  tarjetas con estado, proyecto, tarea, modelo, ojo y PIN. El detalle muestra
  ruta, coste, tokens, última salida y acciones: interrumpir, enviar mensaje,
  fijar, ocultar, abrir carpeta y copiar ID.
- **Hardware:** QR del dispositivo virtual en el panel, URL del panel con botón
  para abrirlo, y dispositivos con estado conectado/desconectado y revocación.
- **Auditoría:** últimas aprobaciones y eventos, con estado y comando.
- **Ajustes:** versión del gateway, fuentes de descubrimiento, ritmos de sondeo
  y **límites reales de las IAs** con sus ventanas, barras y renovación; todo
  sale de `GET /api/info` y `GET /api/limits` y es de solo lectura, salvo el
  **Modo reposo**, el **ojo de cada ventana** y el modo **Restante/Gastado**.
- **Columna lateral del panel:** mitad límites (solo ventanas con ojo abierto,
  porcentaje grande, barra y renovación) y mitad estados de agentes
  (trabajando, esperando, en espera, error), con coste, tokens y conexión al
  pie.
- **Panel:** tras 5 minutos sin actividad entra en reposo con la hora; al volver
  muestra un resumen de lo ocurrido y vuelve al dashboard. Un permiso pendiente
  se avisa en reposo sin despertar la pantalla.
- **Radar de peligro:** nivel 1/4–4/4, motivos humanos y mantener A según el
  riesgo. La app lo muestra en modo consulta.
- Avisos flotantes cuando un agente visible espera, termina o falla; atajos
  `/`, `Esc` y `R`.

Endpoints:

| Ruta | Quién | Qué hace |
|---|---|---|
| `GET /` | cualquiera | Panel |
| `GET /api/health` | cualquiera | Estado mínimo del gateway |
| `POST /api/pair` | código | Emite token (simulador) |
| `GET /api/dev/bootstrap` | loopback | Token de conveniencia del panel |
| `GET /api/dev/pairing` | loopback | Código vigente (simulador) |
| `GET /api/dev/virtual` | loopback + dev | Dispositivo virtual: QR y estado |
| `POST /api/dev/virtual/pair` | loopback + dev | Verifica el código TOTP |
| `POST /api/dev/virtual/confirm` | loopback + dev | Simula la confirmación A |
| `POST /api/dev/virtual/unpair` | loopback + dev | Desempareja el dispositivo virtual |
| `POST /api/dev/virtual/reset` | loopback + dev | Genera id y secreto nuevos |
| `POST /api/dev/approval` | loopback | Dispara una aprobación del agente falso |
| `POST /api/dev/interrupt` | loopback | Interrumpe al agente falso |
| `GET /api/state` | loopback | Snapshot actual |
| `POST /api/agents/{id}/interrupt` | loopback | Interrumpe un agente |
| `POST /api/agents/{id}/message` | loopback | Envía texto a un agente |
| `GET /api/info` | loopback | Configuración, fuentes y contadores |
| `GET /api/config/visibility` | loopback | Lista de agentes ocultos |
| `PATCH /api/config/visibility/{agent_id}` | loopback | Oculta o muestra un agente |
| `GET /api/config/pins` | loopback | Lista de agentes fijados |
| `PATCH /api/config/pins/{agent_id}` | loopback | Fija o desfija un agente (máx. 2) |
| `GET /api/config/rest` | loopback | Minutos de inactividad antes del reposo |
| `PATCH /api/config/rest` | loopback | Cambia y persiste el modo reposo |
| `GET /api/config/remote` | loopback | Token y URLs para control desde otro PC |
| `POST /api/control/pair` | LAN | Vincula la app con el código de Google Authenticator |
| `GET /api/limits` | loopback | Límites de todas las IAs y selección |
| `GET /api/codex/limits` | loopback | Compatibilidad: solo Codex |
| `PATCH /api/config/limits` | loopback | Cambia ventanas (`windows`) y modo (`view`) |
| `GET /api/config/limits` | loopback | Compatibilidad: límites y uso por agente |
| `PATCH /api/config/limits/{agent_id}` | loopback | Compatibilidad: límites por agente |
| `GET /api/audit` | loopback | Aprobaciones y eventos |
| `GET /api/devices` | loopback | Dispositivos y estado conectado |
| `POST /api/devices/{id}/revoke` | loopback | Revoca un token |
| `WS /ws/control` | token | Estado y aprobaciones |
| `WS /ws/audio` | token | PCM + ciclo de vida |

El panel muestra el QR de emparejamiento del dispositivo virtual (o del
hardware real). La app lo escanea con Google Authenticator y confirma desde el
panel; el gateway solo emite el token cuando el emparejamiento termina.

---

## 12. Pruebas

136 pruebas (pytest) sobre las piezas donde un fallo es caro:

- **Estado:** transiciones válidas e inválidas, `since`, limpieza de aprobación,
  orden del dashboard, `seq`, límite del log.
- **Broker:** idempotencia, rechazo, id desconocido, opción inválida, caducidad,
  obsolescencia, `hold_ms`, auditoría.
- **Riesgo:** lectura, alto, crítico, patrón de lectura que no rebaja el riesgo.
- **Protocolo:** parseo, campos desconocidos, `type` desconocido.
- **API:** emparejamiento, token inválido, `hello` ausente, ping/pong, estado,
  permitir, denegar, duplicado, id desconocido, interrupción, audio sin STT,
  caducidad real y re-sincronización de aprobaciones al reconectar.
- **Visibilidad:** GET/PATCH, agente desconocido, `hidden_agents` en `welcome`,
  broadcast `visibility` y persistencia tras reiniciar el gateway.
- **Descubrimiento:** mapeo de sesiones de OpenCode, recencia, orden y tope,
  tokens sin caché, estado por `busy`/`idle` y sincronización (alta, cambio y
  retirada de agentes).
- **Fuentes locales:** Claude Code (JSONL), Codex (catálogo y SQLite legacy,
  sin chats de ChatGPT), Gemini CLI, Antigravity, Cursor y Copilot; normalización
  de fechas y gestión de la sincronización.
- **Salida y aviso:** lectura del último texto o acción de OpenCode, `task`/log
  del agente y transición `RUNNING`/`WAITING_INPUT` → `DONE`/`IDLE` para el ding.
- **Permisos y PTT:** mapeo `allow`/`deny` a `once`/`reject`, prompt e
  interrupción del adaptador, y deduplicación de permisos pendientes.
- **Fijados:** GET/PATCH, agente desconocido, límite de dos (`409 pin_limit`),
  `pinned_agents` en `welcome`, broadcast `pinned` y persistencia.
- **Centro de control:** `/api/info` (configuración, fuentes y contadores) y
  `/api/devices` con el flag `connected`.
- **Límites de las IAs:** normalización de OpenCode, Codex y Claude; ventanas
  Rolling/Semanal/Mensual, presupuestos, selección de proveedores y respuesta
  inválida.

Criterios de salida de Fase A:

- [x] Aprobar/denegar desde el navegador con `approval_id`.
- [x] El doble toque no ejecuta dos veces.
- [x] Una petición caducada no se puede aprobar.
- [x] El panel se reconecta y refleja la caída del gateway.
- [ ] p95 < 150 ms de ida y vuelta en LAN (falta medirlo con hardware real).
- [ ] 24 h de ejecución sin fugas (pendiente de soak).

---

## 13. Límites conocidos de esta fase

1. **Detección de agentes en solo lectura.** OpenCode, Claude Code, Codex,
   Gemini CLI, Antigravity, Cursor y Copilot se detectan por sus datos locales.
   Las aprobaciones y el dictado ya funcionan **solo para OpenCode**; el resto
   sigue en detección. El `FakeAgentAdapter` solo produce aprobaciones simuladas.
2. **No hay STT local todavía.** El panel usa la Web Speech API del navegador;
   el socket de audio del gateway sigue respondiendo `stt_not_configured`.
3. **No hay TLS.** Token sí, cifrado no. No usar fuera de una LAN de confianza.
4. **No hay rate limiting** ni ventana anti-replay.
5. **El panel es un simulador de dispositivo**, no la UI final. La UI real es
   LVGL en 480×320 con D-pad; lo que se valida aquí es el flujo.
6. **Cada pestaña del panel tiene su propio `device_id`** (`baton-web-<id>`) y su
   token en `sessionStorage`; abrir varias pestañas no rota el token. El
   bootstrap sin id genera uno único.
7. **La política de riesgo es heurística.** No sustituye la política del agente.
8. **Los fijados son una preferencia de presentación**, no una prioridad de
   ejecución: un agente fijado no se adelanta en el trabajo, solo en la pantalla.
   El máximo es dos; el tercero se rechaza. Si está oculto, no se muestra.
8. **El coste es informativo** y llega del adaptador; no hay proxy todavía.
9. **No hay heartbeat del servidor**; el `ping` lo inicia el dispositivo. El
   `heartbeat_s` se anuncia en `welcome` para el firmware.

---

## 14. Siguiente fase (0.5)

Objetivo: un agente real aprobando un `Bash` de verdad, y voz con preview.

1. **ClaudeCodeAdapter** con hook HTTP `PermissionRequest`:
   - endpoint local que recibe el hook y espera la decisión;
   - timeout y `onFailure: "continue"` para no bloquear la TUI;
   - mapear `tool_name`, `tool_input.command`, `cwd` a `AgentEvent.approval`;
   - hooks `Stop`/`Notification` para estado y fin de turno.
2. **OpenCodeAdapter** contra `opencode serve`:
   - SSE `/event` para estado y mensajes;
   - `POST /session/:id/permissions/:permissionID` para responder;
   - coste y tokens nativos.
3. **STTService** con VAD + faster-whisper, modelo caliente, `language` y
   `initial_prompt` configurables.
4. **Medición** de latencia y WER con 20 comandos reales en es/ca/en.
5. **TLS** con certificado autofirmado y pinning en el firmware.
6. **Soak** de 24 h y 1.000 aprobaciones.

Criterio para pasar a hardware: usar el panel una semana como pestaña fija y
que las tres primeras hipótesis del plan (detectar antes, −50 % de cambios de
contexto, >70 % de aprobaciones desde el panel) se muevan en la dirección
correcta.

---

## 15. Cómo añadir un agente

1. Crea `baton/adapters/<agente>.py` implementando `AgentAdapter`.
2. En `start(sink)`, abre la conexión nativa (hook, SSE, socket) y emite:
   - `AgentEvent(EventKind.STATUS, id, {"status": "RUNNING", "task": "…"})`
   - `AgentEvent(EventKind.APPROVAL, id, {"approval_id", "kind", "title",
     "command", "cwd", "risk", "reasons"})`
   - `AgentEvent(EventKind.USAGE, id, {"cost_session", "tokens_session"})`
3. Implementa `respond` para llamar a la API nativa del agente y
   `notify_expired` para no tocar nada (dejar el prompt local).
4. Regístralo en `Services.build` y añade una prueba con un adaptador falso que
   reproduzca el mismo contrato.
5. No toques el protocolo: si el agente necesita un campo nuevo, se añade al
   esquema con `proto` incrementado y compatibilidad hacia atrás.
