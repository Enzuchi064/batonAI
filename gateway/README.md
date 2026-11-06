# batonAI — gateway (Fase A)

Gateway local que mantiene el estado de los agentes, arbitra aprobaciones y sirve
un panel web que habla el mismo protocolo que el dispositivo físico.

Esta fase **no** ejecuta todavía aprobaciones de agentes reales ni transcribe
voz: puede incluir agentes de demostración con `--fake` para validar el flujo
completo y, además, detecta las sesiones de **OpenCode, Claude Code, Codex,
Gemini CLI, Antigravity, Copilot y Cursor** que corren en el PC. El diseño y los
límites están en [`../DISENO_SOFTWARE_BATONAI.md`](../DISENO_SOFTWARE_BATONAI.md).
La app de escritorio está en [`../desktop/`](../desktop/README.md).

## Arrancar

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m baton serve
```

Abre <http://127.0.0.1:8765/>. El panel se empareja solo en localhost y muestra
el código vigente en la cabecera.

Si el puerto está ocupado:

```powershell
.\.venv\Scripts\python.exe -m baton serve --port 8770
```

Para probar desde el dispositivo en la LAN (solo red de confianza):

```powershell
.\.venv\Scripts\python.exe -m baton serve --host 0.0.0.0
```

## Detección de agentes

El gateway detecta las sesiones recientes de los principales agentes locales y
las publica como agentes con id `<proveedor>:<sesión>`:

| Agente | Dónde mira | Id |
|---|---|---|
| **OpenCode** | API local de OpenCode | `opencode:<sesión>` |
| **Claude Code** | `~/.claude/projects/**/*.jsonl` | `anthropic:<sesión>` |
| **Codex** | `~/.codex/sqlite/codex.db`, `state_5.sqlite` y `~/.codex/sessions` | `openai:<hilo>` |
| **Gemini CLI** | `~/.gemini/tmp/**/chats/session-*.json` | `google:<sesión>` |
| **Antigravity** | `~/.gemini/antigravity/conversation_summaries.db` | `antigravity:<conversación>` |
| **GitHub Copilot CLI** | `~/.copilot/session-state/**/*.json` (best effort) | `github:<sesión>` |
| **Cursor** | `state.vscdb` del IDE (composers y chats) | `cursor:<sesión>` |

Detalles:

- **OpenCode** descubre el puerto del proceso `opencode-cli` con `psutil`
  (normalmente `127.0.0.1:28894`), lee la contraseña de
  `~/.config/opencode/service.json` y consulta `GET /api/session` con Basic auth.
  La contraseña no se registra ni se envía al dispositivo.
- Con la app de escritorio de OpenCode abierta, se usan sus **pestañas reales**
  (`drafts.sqlite`): al cerrar una pestaña, su agente desaparece en el siguiente
  sondeo. Sin la app, se cae a la recencia de la API.
- **Codex** usa el catálogo nuevo (`local_thread_catalog`) y descarta los chats
  de ChatGPT: solo publica hilos locales. Si no hay catálogo, cae a
  `state_5.sqlite` y a los rollouts JSONL de la CLI.
- **Claude Code** lee el título y el modelo de la transcripción; ignora los
  subagentes.
- **Gemini CLI** lee la sesión JSON; **Antigravity** lee sus resúmenes de
  conversación y su estado (`not_fully_idle`).
- **Copilot** es best effort: si el CLI guarda sesiones en JSON, aparecen; si no,
  no se inventan.
- **Cursor** lee los compositores y chats de su `state.vscdb`; si el IDE no está
  instalado o la base está bloqueada, no se muestra nada.
- Las fuentes de archivos/SQLite muestran las sesiones de las últimas **12 h**
  (máximo 8 por fuente) y se sondean cada **10 s**. Si la sesión se actualizó en
  los últimos **120 s**, se marca `RUNNING`; si no, `IDLE`. OpenCode usa su
  propio `busy`/`idle`.
- Si una fuente deja de responder, sus agentes pasan a `OFFLINE`; al cerrar una
  sesión, desaparecen de la lista.

La **detección** es de solo lectura. Las acciones del panel (aprobar/denegar y
dictado) sí escriben en OpenCode a través de su API por sesión. La app y el
panel muestran el logo del proveedor: Anthropic, OpenAI, Google/Gemini,
Antigravity, OpenCode, GitHub Copilot y Cursor.

## Permisos y dictado

Cuando una sesión de OpenCode tiene un permiso pendiente
(`GET /api/session/{id}/permission`), el gateway lo convierte en la hoja de
aprobación del panel:

- **A** permite (`decision: once`); **B** deniega (`decision: reject`).
- Con riesgo alto/crítico, **A** hay que mantenerlo (1,5 s / 2,5 s).
- El adaptador responde en OpenCode con
  `POST /api/session/{id}/permission/{requestID}/reply`.
- Para que OpenCode pregunte, el proyecto incluye `opencode.json` con reglas
  `ask` para comandos peligrosos (`rm -rf`, force push, sudo, format, shutdown,
  `del /f`…). Amplía esas reglas si quieres que pregunte por más acciones.

El **PTT** del panel usa el reconocimiento de voz del navegador (Web Speech API):
mantén PTT, habla, suelta y revisa el texto; **A** lo envía a la sesión abierta
con `POST /api/session/{id}/prompt`. El navegador debe tener permiso de
micrófono para `127.0.0.1:8770`; si está bloqueado, el panel lo avisa y **no
inventa texto**. Si el panel se abre dentro de OpenCode y no tiene micrófono,
ábrelo en Chrome/Edge. El hardware usará STT local en el gateway (pendiente).

## Salida y aviso

- La tarjeta del agente muestra su **última salida**: el texto del asistente o,
  si está ejecutando una herramienta, la acción y su comando/ruta.
- El detalle conserva las últimas líneas de actividad.
- Cuando un agente **visible** pasa de `RUNNING`/`WAITING_INPUT` a `DONE`/`IDLE`,
  el panel reproduce un **ding** de dos tonos. Los ocultos no suenan.
- En el navegador el audio necesita una primera interacción (política de
  autoplay). En el hardware sonará por el MAX98357A cuando exista el firmware.

## Fijados

En la app de escritorio, el **PIN** junto al ojo fija un agente. El gateway
mantiene como máximo **dos** fijados:

- `GET /api/config/pins` y `PATCH /api/config/pins/{agent_id}`.
- El `welcome` incluye `config.pinned_agents`; al cambiar se emite `pinned`.
- El panel 480×320 coloca los fijados **arriba del todo** (máx. 2), con una
  marca de pin. El resto sigue el orden normal por estado.
- Un agente oculto no se muestra aunque esté fijado: manda el ojo.
- Si una sesión desaparece y vuelve, conserva su pin.

## Centro de control

La app de escritorio tiene cuatro pestañas:

- **Agentes:** visibilidad (ojo) y fijados (PIN).
- **Hardware:** dispositivo virtual con QR TOTP, código del panel, URL del panel
  y dispositivos con botón para revocar.
- **Auditoría:** últimas aprobaciones y eventos del gateway.
- **Ajustes:** estado del gateway (`/api/info`), fuentes de descubrimiento,
  límites reales de las IAs y ritmos de sondeo.

### Acciones sobre agentes

- `POST /api/agents/{id}/interrupt` interrumpe la tarea del agente.
- `POST /api/agents/{id}/message` con `{"text": "..."}` envía una instrucción.

Ambos son solo loopback, responden `404` si el agente no existe y `409` si su
adaptador no admite la acción. El supervisor registra `agent_interrupted` y
`text_injected` en la auditoría.

### Modo reposo

- `GET /api/config/rest` devuelve `rest_after_s` (300 por defecto).
- `PATCH /api/config/rest` con `{"rest_after_s": 600}` lo cambia y lo persiste
  en SQLite.
- `0` desactiva el modo reposo. El panel lo lee al arrancar y cada 30 s.
- El panel muestra la hora y un resumen al volver; las decisiones siguen siendo
  solo del dispositivo.

### Control remoto

- El ejecutable instalado escucha en `0.0.0.0:8770` para permitir el control
  desde otro PC de la red privada.
- Las peticiones desde loopback no necesitan token.
- Las peticiones desde LAN requieren `Authorization: Bearer <token>`.
- El token se genera la primera vez y se guarda en `settings.remote_token` de
  SQLite.
- `GET /api/config/remote` (solo loopback) devuelve token, URL principal e
  interfaces disponibles.
- El instalador crea la regla de firewall para `batonAI-gateway.exe` en el
  perfil Privado.

### Límites reales de las IAs

- `GET /api/limits` agrega todas las fuentes instaladas:
  - `providers[]`: cada IA con `id`, `label`, `installed`, `selected`, `ok`,
    `plan`, `windows[]`, `budgets[]`, `error` y `read_at`.
  - `windows[]`: `key` (`opencode:rolling`), `id`
    (`rolling`/`weekly`/`monthly`), etiqueta, porcentaje usado y restante,
    `selected`, `resets_at` y duración.
  - `selected_windows`, `period` y `view` (`remaining`/`used`).
- **OpenCode:** consulta `/api/experimental/usage/limits` del servidor local,
  reutilizando el puerto y la contraseña que ya usa el descubrimiento.
- **Codex:** lanza `codex app-server --listen stdio://` y pide
  `account/rateLimits/read`; no necesita API key adicional.
- **Claude Code:** usa el token de `~/.claude/.credentials.json` o
  `CLAUDE_CODE_OAUTH_TOKEN` contra `/api/oauth/usage`.
- `PATCH /api/config/limits` cambia las ventanas visibles (`windows`), el modo
  (`view`: `remaining`/`used`) y, por compatibilidad, `providers` o `period`.
  Se persisten en `settings.ticker_windows` y `settings.limits_view`.
- `LIMITS_ENABLED`, `LIMITS_POLL_S`, `OPENCODE_LIMITS_ENABLED`,
  `CLAUDE_LIMITS_ENABLED`, `CODEX_USAGE_ENABLED`, `CODEX_USAGE_POLL_S` y
  `BATON_CODEX_EXE` controlan las fuentes.
- `individualLimit` de Codex se expone como `spend_control`, no como ventana
  mensual.
- Los endpoints `GET/PATCH /api/config/limits/{agent_id}` y las tablas
  `agent_limits` / `agent_usage_daily` quedan por compatibilidad, pero la app y
  la cinta ya no los usan.
- La columna de límites del panel solo muestra las ventanas con ojo abierto; no
  estados ni coste.

### Radar de peligro

- El clasificador devuelve `reasons` técnicos y `details` para humanos.
- `approval_request` incluye `details`; el estado incluye `risk_reasons` y
  `risk_details`.
- La auditoría guarda `risk_details` y los muestra en la app.
- Las decisiones siguen siendo solo del dispositivo.

### Dispositivo virtual TOTP

`GET /api/dev/virtual` devuelve un dispositivo simulado con QR `otpauth://`
(SVG), `device_id`, estado y, solo en modo desarrollo, el código actual. El QR
se pinta en el panel 480×320 (`/`), no en la app. Sirve para probar el flujo de
emparejamiento sin ESP32:

1. Abre el panel (`/`): muestra el QR.
2. Escanéalo con Google Authenticator.
3. En la app, **Hardware** → escribe el código y pulsa **Emparejar**.
4. La primera vez, el panel muestra el PC y el SAS; pulsa **A** en el panel.
5. El panel se conecta con el token y pasa al dashboard. Los reemplazos no
   piden A.

Endpoints: `POST /api/dev/virtual/pair`, `/confirm`, `/cancel`, `/unpair` y
`/reset` (todos solo loopback y con `BATON_DEV_MODE=1`). El estado se guarda en
`var/virtual_device.json` para conservar el secreto entre reinicios.

## Qué probar

Sin `--fake` el panel solo muestra **agentes reales**. Para probar las
aprobaciones con el agente de demostración, arranca con `--fake`; los botones
**simular permiso** y **riesgo alto** aparecen solo en ese modo.

La interfaz está renderizada a **480×320**, el mismo tamaño que la pantalla del
dispositivo, dentro de una carcasa clamshell con tres botones y un encoder.
Hay una vista estática de referencia en
<http://127.0.0.1:8765/static/preview-dashboard.html>.

Los controles de la base son interactivos:

| Control | Acción |
|---|---|
| **A** (verde) | Confirma: abre el detalle del agente; en la modal confirma la opción enfocada (mantener si es permitir con riesgo alto) |
| **B** (negro) | Vuelve atrás: cierra el detalle; en la modal cancela la petición y vuelve al dashboard |
| **PTT** (azul) | En la conversación, mantener para dictar; al soltar aparece la transcripción simulada y **A** la envía |
| **Encoder** (naranja) | Girar para mover la selección; en la modal elige entre permitir y denegar |

1. El agente falso trabaja, termina y vuelve a `IDLE` por ciclos. No pide
   permisos por su cuenta: eso se hace con los botones de desarrollo.
2. Al pulsar **simular permiso**, la aprobación aparece como **hoja inferior**:
   el dashboard sigue visible detrás y el encoder elige la opción.
3. Haz clic en una tarjeta (o pulsa **A**) para abrir la **conversación** del
   agente. Es la pantalla donde se usa el PTT: mantén PTT, suelta y aparecerá una
   transcripción simulada; **A** la envía y **B** la cancela.
4. **simular permiso** fuerza una aprobación normal: se resuelve con `A` o clic.
5. **simular riesgo alto** fuerza `rm -rf`: el botón exige mantener 1,5 s. Al
   soltar antes, no pasa nada.
6. `B` deniega. Repetir la respuesta no ejecuta dos veces: devuelve
   `duplicate: true`.
7. Dejar una petición 60 s sin responder: caduca y el agente queda en `IDLE`.
8. Parar el gateway: el panel muestra "Gateway desconectado" y reconecta al
   volver.
9. **auditoría** lista las aprobaciones con su resultado y dispositivo.
10. Desde la app de escritorio (`../desktop/`), apaga el ojo de un agente: el
    panel deja de mostrarlo, de contarlo y de avisar. La elección se guarda en el
    gateway y sigue ahí tras reiniciar.
11. Pulsa el **PIN** de hasta dos agentes: el panel los coloca arriba y los
    marca. Un tercero se rechaza hasta que desfijes uno.
12. En la app, revisa **Hardware** (código, dispositivos y revocar),
    **Auditoría** (aprobaciones/eventos) y **Ajustes** (gateway y detección).

Atajos del panel: `A` permitir, `B` denegar, `←`/`→` cambiar de agente,
`Esc` cerrar la auditoría. Con riesgo alto, `A` hay que mantenerla.

## Comandos

```powershell
.\.venv\Scripts\python.exe -m baton serve [--host H] [--port P] [--fake]
.\.venv\Scripts\python.exe -m baton pair      # imprime un código y sale
.\.venv\Scripts\baton.exe serve               # mismo CLI, instalado
.\.venv\Scripts\python.exe -m pytest -q       # 135 pruebas
```

## Estructura

| Archivo | Responsabilidad |
|---|---|
| `baton/api.py` | HTTP, WebSocket de control y audio, emparejamiento |
| `baton/services.py` | Ensamblaje y despacho de mensajes del dispositivo |
| `baton/state.py` | Estados y transiciones del agente |
| `baton/broker.py` | Aprobaciones: identidad, caducidad, idempotencia |
| `baton/risk.py` | Clasificación de riesgo y `hold_ms` |
| `baton/adapters/supervisor.py` | Une adaptadores, estado, broker y hub |
| `baton/discovery.py` | Descubre sesiones de OpenCode y sincroniza agentes |
| `baton/local_agents.py` | Descubre Claude Code, Codex, Gemini, Antigravity, Cursor y Copilot |
| `baton/limits.py` | Agrega las fuentes de límites y su selección |
| `baton/opencode_usage.py` | Lee los límites reales del servidor de OpenCode |
| `baton/codex_usage.py` | Lee los límites reales del app-server de Codex |
| `baton/claude_usage.py` | Lee los límites reales de Claude Code |
| `baton/audit.py` | SQLite de dispositivos, aprobaciones y eventos |
| `baton/adapters/fake.py` | Agente de demostración |
| `baton/static/` | Panel web sin build |

## Configuración

Variables `BATON_*` (`HOST`, `PORT`, `DB_PATH`, `APPROVAL_TIMEOUT_S`,
`HEARTBEAT_S`, `LOG_TAIL`, `FAKE_AUTOSTART`, `FAKE_AGENTS`, `FAKE_APPROVALS`,
`DEV_MODE`, `OPENCODE_ENABLED`, `OPENCODE_URL`, `OPENCODE_PASSWORD`,
`OPENCODE_RECENCY_S`, `OPENCODE_MAX_SESSIONS`, `OPENCODE_POLL_S`,
`LOCAL_AGENTS_ENABLED`, `LOCAL_AGENTS_RECENCY_S`, `LOCAL_AGENTS_MAX_SESSIONS`,
`LOCAL_AGENTS_POLL_S`, `LOCAL_AGENTS_ACTIVE_S`, `LIMITS_ENABLED`,
`LIMITS_POLL_S`, `OPENCODE_LIMITS_ENABLED`, `CLAUDE_LIMITS_ENABLED`,
`CODEX_USAGE_ENABLED`, `CODEX_USAGE_POLL_S`, `BATON_CODEX_EXE`). La tabla
completa está en el documento de diseño, sección 11.

La base de datos vive en `var/baton.db` y no se versiona. Para empezar de cero,
bórrala con el gateway parado.

## Notas

- Los endpoints `/api/dev/*`, `/api/state`, `/api/info`, `/api/config/visibility`,
  `/api/config/pins`, `/api/devices` y `/api/audit` solo responden a loopback.
- La visibilidad de los agentes vive en `agent_visibility` (SQLite) y se expone
  con `GET`/`PATCH /api/config/visibility`. El panel y el dispositivo la reciben
  en `welcome` (config) y en el mensaje `visibility`.
- Los fijados viven en `agent_pins` (máximo 2) y se exponen con
  `GET`/`PATCH /api/config/pins`; viajan en `welcome.config.pinned_agents` y en
  el mensaje `pinned`. Si un fijado está oculto, no se muestra.
- El panel usa un dispositivo de conveniencia por pestaña (`baton-web-<id>`) con
  su token en `sessionStorage`; abrir varias pestañas ya no se rota el token.
- Sin TLS todavía: úsalo en local o en una LAN de confianza.
