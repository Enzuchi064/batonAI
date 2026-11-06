# batonAI — Roadmap de software (v0.2)

Estado de partida: gateway funcional (93 pruebas en verde), panel web 480×320,
app de escritorio, descubrimiento de 7 agentes, aprobaciones reales de OpenCode
y agente falso. **No hay**: TLS, autorización por dispositivo, STT, firma de
auditoría, empaquetado ni control de versiones.

Este documento ordena todo lo que queda por hacer en software. No es una lista
de deseos: cada bloque tiene criterio de salida.

## 0. Cómo leerlo

- **P0** — bloquea usar el gateway fuera de `localhost` o vender nada.
- **P1** — necesario para el siguiente hito.
- **P2** — mejora real, pero puede esperar.
- **S** ≤ 1 día · **M** 2–5 días · **L** 1–2 semanas.
- Cada idea tiene un id (`S3`, `A1`, `U7`) para poder referenciarla en issues.

## 1. Estado real (lo que ya está)

| Área | Hecho | Falta |
|---|---|---|
| Protocolo | JSON v1, `approval_id`, caducidad, idempotencia, `proto` handshake | v2: capacidades, audio, config push |
| Estado | 6 estados, orden por prioridad, `log_tail`, coste/tokens | Detección de atascos, presupuesto |
| Aprobaciones | Broker con caducidad, supersede, riesgo y `hold_ms` | Verificación servidor, scopes |
| Dispositivos | Pairing con código, tokens hasheados, revocación | Rate limit, TLS, permisos |
| Agentes | OpenCode (permisos reales) + 6 fuentes de solo lectura | Claude Code hook, Codex permisos |
| Panel | Dashboard, detalle, modal, PTT simulado, auditoría | Diff, cola, métricas |
| Escritorio | Visibilidad y pins | Arrancar gateway, dispositivos, reglas |
| Voz | Nada (el panel usa Web Speech del navegador) | STT local, VAD, preview |
| Operación | `serve`, `pair`, pytest | Servicio Windows, logs, migraciones |

## 2. Track S — Seguridad (P0/P1)

Hallazgos verificados en el código actual, no hipótesis.

### S1. Rate limit y bloqueo en `/api/pair` — P0, S
El código es de 6 dígitos (1.000.000 combinaciones), TTL de 600 s y **no hay
límite de intentos**. Con `--host 0.0.0.0`, cualquiera en la LAN puede probar
miles de códigos y emparejar un dispositivo propio, que luego puede aprobar.

- Límite por IP y global (p. ej. 5/min, 20/hora), backoff exponencial.
- Tras 10 fallos, rotar el código y registrar `pair_denied` en `events`.
- TTL de 90 s (no 600) y código de 8 caracteres o 3 palabras.
- Comparación constante ya existe (`compare_digest`), conservarla.
- Archivos: `pairing.py`, `api.py`, `config.py`, `audit.py`, tests.

### S2. TLS obligatorio fuera de loopback — P0, M
Hoy el token de dispositivo, las aprobaciones y el audio viajan en claro por
`ws://`. Un sniffer en la LAN roba el token y aprueba comandos.

- `baton serve --tls` con certificado autofirmado generado en `var/tls/`.
- **Fail-closed**: si `host != 127.0.0.1` y no hay TLS, negarse a arrancar.
- Huella SHA-256 del certificado en el `welcome` para que el firmware fije.
- Rotación de certificado y endpoint para republicar la huella.
- Archivos: nuevo `baton/tls.py`, `__main__.py`, `api.py`, `config.py`.

### S3. Endurecer el bootstrap del panel web — P0, M
`/api/dev/bootstrap` emite un token de dispositivo a **cualquier proceso local**
sin prueba de intención, y `dev_mode` vale `True` por defecto. Es una puerta
trasera cómoda hoy y un agujero el día que alguien instale esto.

- `dev_mode=False` por defecto; `--dev` explícito para activarlo.
- Ticket de un solo uso (nonce de 30 s) para el primer emparejamiento del panel.
- Token del panel con scope `view` + `approve` + `inject`, nunca `admin`.
- Archivos: `config.py`, `pairing.py`, `api.py`, `static/app.js`.

### S4. Host, Origin y cabeceras — P0, S
No hay `TrustedHostMiddleware`, ni comprobación de `Origin` en el WebSocket, ni
CSP. Eso permite **DNS rebinding**: una web maliciosa resuelve su dominio a
`127.0.0.1` y habla con tu gateway.

- `TrustedHostMiddleware` con `127.0.0.1`, `localhost` y el host configurado.
- Rechazar `Upgrade` cuyo `Origin` no sea el panel o esté vacío en modo nativo.
- Cabeceras: `Content-Security-Policy` (sin `unsafe-inline`), `X-Frame-Options:
  DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- Archivos: `api.py`, `static/index.html`.

### S5. Autorización por dispositivo y por agente — P1, M
Hoy **cualquier** dispositivo emparejado puede aprobar **cualquier** agente,
interrumpirlo y dictarle. Un token filtrado es control total.

- Tabla `device_scopes(device_id, scope)` con `view|approve|inject|interrupt|admin`.
- ACL opcional por agente (`device_agents`) para modo "solo esta sesión".
- `services.handle_client_message` valida el scope antes de actuar.
- Registrar `permission_denied` en auditoría.
- UI de escritorio para gestionar scopes.
- Archivos: `audit.py` (+ migración), `services.py`, `api.py`, `desktop/`.

### S6. El `hold_ms` y el `confirm` son del cliente — P1, M
`InjectText.confirm` lo pone el dispositivo: un cliente modificado envía
`confirm:true` y se salta la confirmación. El "mantener pulsado" de riesgo alto
tampoco lo puede verificar el gateway.

- Sustituir `confirm` por un `preview_token` emitido por el servidor tras
  `POST /api/text/preview` y válido 60 s para ese agente y ese texto (hash).
- Para riesgo alto/crítico: registrar `delivered_at` por dispositivo y rechazar
  respuestas que lleguen antes de `hold_ms` (garantía de servidor, no de UI).
- Opción "doble canal" para crítico: aprobar exige panel + confirmación en el PC.
- Archivos: `protocol.py` (v2), `services.py`, `broker.py`, `api.py`.

### S7. Redacción y cifrado de la auditoría — P1, M
`approvals.command` guarda el comando tal cual. Un `curl -H "Authorization:
Bearer …"` acaba en SQLite en claro, para siempre.

- Filtro de redacción (`Authorization`, `Bearer`, `--password`, `-H`, `*_TOKEN`,
  `*_KEY`, cadenas largas tipo JWT) antes de persistir y de loguear.
- Cifrado en reposo: DPAPI en Windows o SQLCipher; como mínimo ACL del archivo.
- Retención configurable (30/90 días) y `baton purge --older-than`.
- Cadena de hashes por fila para detectar manipulación; `baton audit --verify`.
- Archivos: nuevo `baton/redact.py`, `audit.py`, `broker.py`, `supervisor.py`.

### S8. Límites de recursos y DoS — P1, S
Hay límites de tamaño por frame, pero no de tasa ni de duración total.

- Máx. conexiones totales y por IP; máx. mensajes/s por conexión.
- Audio: duración máxima (60 s) y bytes totales; cerrar con `error` si se excede.
- Timeout en endpoints HTTP y en `pair`.
- Máx. 1 aprobación pendiente por agente (ya existe por `supersede`), conservarlo.
- Archivos: `api.py`, `config.py`, `hub.py`.

### S9. Secretos y `baton doctor` — P1, S
- Verificar que `OPENCODE_PASSWORD` y el contenido de `service.json` nunca
  aparecen en logs, errores ni auditoría (test explícito).
- Avisar si `var/baton.db` o `var/` tienen permisos amplios.
- `baton doctor`: TLS, dev_mode, tokens sin usar, adaptadores caídos, tamaño de DB.
- Archivos: nuevo `baton/doctor.py`, `__main__.py`.

### S10. Modelo de amenazas escrito — P1, S
Dos páginas en `SEGURIDAD_BATONAI.md`: activos (token, aprobaciones, audio,
auditoría), adversarios (LAN, web con DNS rebinding, proceso local, dispositivo
robado, agente comprometido) y control asociado. Evita decisiones incoherentes.

### S11. Cadena de suministro y CI — P0, S
El proyecto **no es un repositorio git**. Sin eso no hay revisión, ni rollback,
ni CI.

- `git init`, `.gitignore` para `.venv/`, `var/`, `__pycache__/`.
- Workflow: ruff + mypy + pytest (3.11/3.13/3.14) + `pip-audit`.
- Lockfile (`uv lock` o `pip-tools`) y versiones fijadas en `pyproject.toml`.
- Archivos: `.github/workflows/ci.yml`, `pyproject.toml`.

### S12. Endurecimiento del dispositivo (gateway-side) — P2, M
- Rotación de token por dispositivo y "revocar todos".
- Pairing mostrando el código en la pantalla del propio dispositivo.
- Atestación mínima: el firmware envía versión y hash de build; el gateway avisa
  si es desconocido.
- Archivos: `pairing.py`, `protocol.py`, `audit.py`.

## 3. Track F — Fundaciones y operación

### F1. Migraciones de SQLite — P0, S
Hoy el esquema se crea con `CREATE TABLE IF NOT EXISTS`: añadir una columna
rompe instalaciones existentes. Usar `PRAGMA user_version` + migraciones
numeradas y un test de "base antigua → base nueva". (`audit.py`)

### F2. Servicio Windows y arranque — P1, M
- `baton service install/uninstall/status` (NSSM o `pywin32`).
- Instancia única (lock en `var/baton.lock`), arranque automático, reinicio ante
  caída, apagado ordenado (cerrar WS, `stale` de aprobaciones, cerrar DB).
- Tray opcional en la app de escritorio con "abrir panel", "estado", "salir".

### F3. Logs y diagnóstico — P1, S
- Logging estructurado JSON con `request_id`, rotación por tamaño.
- Redacción aplicada también aquí (S7).
- `baton diag` genera un zip con versión, config sin secretos, últimas 500
  líneas y estado de adaptadores. Es lo que pedirás cuando alguien diga "no va".

### F4. Configuración validada — P1, S
- `pydantic-settings` con validación, `baton.toml` generado y comentado.
- Precedencia clara: CLI > entorno > archivo > defecto.
- Recarga en caliente solo de lo seguro (visibilidad, pins, DND, reglas).

### F5. Pruebas de resistencia — P1, M
- Contrato común para adaptadores (mismo test contra fake y contra cada real).
- Property-based tests de `broker` y `state` (transiciones imposibles).
- Soak 24 h y 1.000 aprobaciones; caos: matar DB, cortar red, matar agente.
- Fixtures de logs reales, anonimizados, para no depender del PC de cada uno.

### F6. Empaquetado y releases — P2, M
- `pipx`/`uvx` para el gateway, PyInstaller para la app de escritorio.
- Versión en `welcome` y handshake de compatibilidad panel/escritorio/firmware.
- `baton --version`, changelog y etiquetas.

## 4. Track A — Agentes y adaptadores

### A1. Claude Code con hooks — P1, M
La pieza que falta para que el panel sea útil con el agente más usado.

- Hook `PermissionRequest` → endpoint local; esperar decisión con timeout y
  `onFailure: "continue"` para no bloquear la TUI.
- Mapear `tool_name`, `tool_input.command`, `cwd` a `AgentEvent.APPROVAL`.
- Hooks `Notification` y `Stop` para `WAITING_INPUT` y fin de turno.
- `baton install-hooks` que escribe el hook en la config del usuario (no solo en
  este repo: hoy `opencode.json` solo aplica si el agente corre aquí).

### A2. Codex — P1/M, P2/L
- Estado y fin de turno desde su catálogo (ya hay descubrimiento).
- Permisos nativos solo si la versión expone app-server; si no, marcar el agente
  como **solo lectura** en la UI en vez de fingir que se puede aprobar.

### A3. Matriz de capacidades — P1, S
`AgentAdapter.capabilities()` → `{view, approve, inject, interrupt, usage}`.
El panel muestra "solo lectura" o "dictado no disponible" en lugar de un botón
que no hace nada. Es honestidad de producto y evita soporte.

### A4. Degradación y salud de adaptadores — P1, S
- Detectar versión del agente y avisar si el adaptador no la soporta.
- `/api/health` con estado por fuente y último error.
- Backoff al reconectar; nunca bloquear el bucle principal.

### A5. Wrapper `baton run <agente>` — P2, L
Último recurso para agentes sin API: PTY propio con semántica limitada. Debe
anunciarse como "modo degradado", no como integración nativa.

### A6. Agrupación por proyecto — P2, M
Agrupar sesiones por repo (`cwd` → raíz git), no por agente suelto. Permite
detectar dos agentes en el mismo repo y ordenar el dashboard por proyecto.

## 5. Track V — Voz

### V1. STT local con preview — P1, L
- `faster-whisper` + VAD en el gateway, modelo caliente, `language` y
  `initial_prompt` configurables.
- Flujo obligatorio: grabar → transcribir → **preview** → confirmar → enviar.
- Nunca enviar sin confirmación; el audio no sale del PC.
- Medir p50/p95 y WER con 20 comandos reales en es/ca/en y elegir modelo con
  datos, no con intuición.

### V2. Protocolo de audio v2 — P1, M
- Transcripción parcial (`interim`) opcional, cancelación, duración máxima.
- Validar `sample_rate`/`format` (hoy son campos de texto).
- Un solo PTT activo por dispositivo; rechazar solapes.

### V3. Inyección de texto segura — P1, M
- Idempotencia por `message_id` (reintentos no duplican).
- `preview_token` del servidor (ver S6).
- Política por agente y por proyecto: permitir dictado solo en sesiones marcadas.

### V4. Privacidad de voz — P1, S
Audio solo en memoria; sin dump por defecto; `--debug-audio` explícito que avisa.
Si algún día hay nube, opt-in por sesión y borrado verificado.

### V5. Wake word / TTS — P2, L
Solo si el PTT demuestra quedarse corto. Hoy es coste, falsos positivos y
superficie de ataque nueva.

## 6. Track U — Producto y UX del panel

### U1. Medir las hipótesis — P1, M
Es lo que decide si el hardware merece la pena.

- `GET /api/metrics`: tiempo hasta ver `WAITING_INPUT`, aprobaciones por origen,
  cambios de contexto (hook de foco en Windows), días de uso.
- Informe matinal de 10 s con datos de `audit.db`.

### U2. Preview de diff — P1, M
Para `Edit`/`Write`, mostrar archivo y `+12/−3` con las 3 líneas clave, no el JSON
del tool. Es la mejora de confianza más grande del panel.

### U3. Detector "atascado vs pensando" — P1, S
`RUNNING` sin evento nuevo en N min y sin tool en curso → "¿colgado?".
Distinguir esto de "pensando" evita interrupciones innecesarias.

### U4. Conflicto de repo — P1, S
Dos agentes con el mismo `cwd`/repo → aviso en el dashboard. El fallo más caro y
el más fácil de detectar con lo que ya hay.

### U5. Escalada de aviso — P1, M
LED tenue → ding → encender pantalla → push → buzzer, según minutos bloqueado,
riesgo y si estás delante del PC (`GetLastInputInfo`). Incluye "no molestar" y
horario silencioso.

### U6. Reglas aprendidas — P2, M
Tras N aprobaciones iguales, proponer una regla `allow` para la config del
agente, mostrando el diff y pidiendo confirmación. Sale del `audit.db`.

### U7. `baton notify` y fuentes genéricas — P1, M
El cacharro deja de depender de 7 adaptadores frágiles.

- CLI: `baton notify --wait "npm run build"` y webhook HTTP.
- Modelo `Source` (id, título, estado, último mensaje, prioridad) separado de
  `Agent`, para CI, backups, descargas y tests largos.
- El panel muestra fuentes junto a agentes, con el mismo orden por prioridad.

### U8. PWA de bolsillo — P2, M
El gateway ya sirve el panel; con QR de emparejamiento y Web Push se aprueba
desde el móvil sin hardware. Cero firmware nuevo.

### U9. Cola de atención — P1, S
Hoy el dashboard ordena, pero no explica la cola. Mostrar "2 te necesitan",
antigüedad del bloqueo y qué se resuelve primero (bloqueante > error > resto).

### U10. Presupuesto de contexto y coste — P2, M
Avisar cuando una sesión se acerca al límite de contexto o a un coste fijado.
OpenCode ya expone tokens; el resto, si puede.

## 7. Track D — App de escritorio

- **D1** Arrancar/parar el gateway desde la app y asistente de primera ejecución (P1, M).
- **D2** Gestión de dispositivos: listar, renombrar, revocar, scopes, QR de
  emparejamiento (P1, M). Sin esto, S5 no se puede administrar.
- **D3** Editor de reglas: riesgo, allow-list, no molestar, idioma (P2, M).
- **D4** Diagnóstico: salud de adaptadores, logs, `baton diag` (P1, S).
- **D5** Autoarranque, bandeja y auto-update (P2, M).

## 8. Track H — Interfaz con el firmware (lo que el gateway debe cambiar)

Antes de escribir firmware, cerrar esto para no rehacerlo.

- **H1** Protocolo v2: `capabilities`, config push, audio v2, `message_id`
  (P1, M). Mantener compatibilidad hacia atrás un major.
- **H2** Pairing pensado para pantalla: código visible, TTL corto, reintento
  con backoff, token guardado en NVS (P1, M).
- **H3** TLS con pinning y rotación de certificado (P1, M).
- **H4** OTA: manifiesto firmado, versión, rollback y estado por dispositivo
  (P2, M).
- **H5** Telemetría por dispositivo: latencia, reconexiones, RSSI, versión (P2, S).
- **H6** Cliente de dispositivo falso en CI que ejecute el protocolo completo
  (pair → welcome → state → approval → ack → reconexión). Es la red de seguridad
  del firmware antes de tener hardware (P1, S).

## 9. Track O — Orquestación nivel 2 (no antes de U1)

- **O1** Cola de tareas con dependencias y estados (P2, L).
- **O2** Handoff entre agentes con contexto resumido (P2, L).
- **O3** Límites: máximo de agentes concurrentes, presupuesto por proyecto (P2, M).
- **O4** Políticas por proyecto: auto-aprobar riesgo bajo, denegar siempre ciertas
  rutas (P2, M).

Condición para empezar: U1 demuestra que el panel se usa a diario durante 14 días.

## 10. Track X — Distribución

- **X1** Instalador de Windows, guía de primeros 10 minutos, modo demo (P1, M).
- **X2** Privacidad y telemetría opt-in, local por defecto (P2, S).
- **X3** Matriz de compatibilidad versiones agente ↔ adaptador, con aviso en UI
  (P1, S).
- **X4** Licencia y modelo de venta del kit, si hay demanda (P2, —).

## 11. Secuencia recomendada

| Hito | Duración | Contenido | Criterio de salida |
|---|---|---|---|
| **M0. Blindaje local** | 1 semana | S1, S3, S4, S11, F1, S8 básico | El panel funciona igual; no hay fuerza bruta ni token para cualquier proceso; CI en verde |
| **M1. LAN segura** | 1–2 semanas | S2, S5, S6, S7, S9, S10, D2 | Se puede usar desde otro equipo de la LAN sin regalar el control; auditoría sin secretos |
| **M2. Fase 0.5 real** | 2–3 semanas | A1, A3, A4, V1, V2, U1, H6 | Aprobar un `Bash` real de Claude Code y dictar con preview; una semana de uso |
| **M3. Uso diario** | 3–4 semanas | U2–U5, U9, A2, F2–F5, D1, D3, D4 | 14 días usándolo sin tocar el PC para aprobar |
| **M4. Hardware** | en paralelo | H1–H4 + firmware F2 del otro documento | El dispositivo físico hace el mismo recorrido que H6 |
| **M5. Producto** | si hay demanda | X1–X3, U7, U8, O1–O4 | 3–5 personas lo montan sin ayuda |

**Si solo tienes 10 horas esta semana:** S11 (git + CI), S1 (rate limit), S4
(Host/Origin/CSP), F1 (migraciones) y U4 (conflicto de repo). Son baratas, no
rompen nada y quitan los dos riesgos que más caro se pagan.

## 12. Deuda técnica concreta detectada

| Dónde | Qué | Arreglo |
|---|---|---|
| `supervisor.py` | `_schedule_broadcast(immediate=True)` ignora el parámetro | Eliminarlo o usarlo de verdad |
| `supervisor.py` | `interrupt()` y `send_text()` devuelven `result is not False`, así que `None` cuenta como éxito | Devolver `bool(result)` explícito y probarlo |
| `services.py` | `/api/dev/interrupt` apunta a `"claude-code"` fijo | Aceptar `agent_id` o retirar el endpoint |
| `pairing.py` | `_issue` borra el dispositivo anterior con el mismo id (rotación silenciosa) | Decidir si rotar o rechazar; registrarlo |
| `hub.py` | Dos conexiones con el mismo `device_id`: gana la última | Notificar al dispositivo desplazado y auditar |
| `pyproject.toml` | Dependencias con `>=` y sin lockfile | Fijar y bloquear |
| `api.py` | `LOCAL_HOSTS` no contempla IPv4 mapeada en IPv6 ni proxies | Normalizar la IP y documentar el supuesto |
| `audit.py` | Esquema sin versión | `PRAGMA user_version` + migraciones (F1) |

## 13. Decisiones abiertas

1. ¿El panel web sigue siendo un dispositivo de pleno derecho o pasa a ser solo
   administración cuando exista hardware?
2. ¿Aprobación crítica con doble canal (panel + PC) o solo `hold_ms` verificado?
3. ¿El gateway se instala como servicio o vive dentro de la app de escritorio?
4. ¿Cifrado de auditoría con DPAPI, SQLCipher o ambos?
5. ¿Se soportan varios PC con un panel (federación) o sigue siendo uno?
6. ¿`baton notify` comparte modelo con agentes o va en una pestaña aparte?

## 14. Definición de "hecho" para software

- Prueba automatizada del camino feliz y del fallo (timeout, token inválido,
  frame grande, agente caído).
- Error visible para el usuario, nunca silencio ni dato inventado.
- Sin secretos en logs, auditoría ni mensajes de error.
- Documentado en `README` o en el diseño, con la variable `BATON_*` si aplica.
- Compatibilidad: un dispositivo con proto anterior sigue funcionando o recibe
  un error claro y no se queda colgado.
