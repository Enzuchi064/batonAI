# Radar de peligro

Feature del dispositivo para que, cuando un agente pida permiso, el usuario
entienda **qué quiere hacer y por qué es peligroso** sin leer un comando a
ciegas.

> Estado: **implementado** en el panel (radar, nivel, motivos y anillo de
> mantener A). La app muestra el permiso en modo consulta.
>
> Principio: las decisiones se toman **solo en el dispositivo**. La app puede
> mostrar el permiso en modo consulta, pero no tiene botones para aprobar ni
> denegar.

---

## 1. Objetivo

Convertir el aviso actual:

> «Permiso requerido · riesgo alto · `git clean -fdx`»

en algo que se entienda en dos segundos:

> **ALTO · 3/4**
> Quiere borrar archivos que no están en Git.
> `git clean -fdx`
> Mantén A 1,5 s para permitir.

El usuario no necesita saber qué es `-fdx`. Necesita saber que va a perder
archivos.

---

## 2. Qué ve el usuario

La pantalla de 480×320 muestra una hoja de aprobación con un radar a la
izquierda y la explicación a la derecha:

```
┌──────────────────────────────────────────────────┐
│  OpenCode · baton-api            +2 en cola  0:42│
│                                                  │
│   ╭─────────╮   ¿Qué quiere hacer?               │
│   │  RADAR  │   git clean -fdx                   │
│   │  ALTO   │   C:\dev\baton-api                 │
│   │  3 / 4  │                                    │
│   ╰─────────╯   Por qué:                          │
│                 • Borra archivos no versionados.  │
│                 • No se pueden recuperar.         │
│                                                  │
│   [ Permitir ]        [ Denegar ]                │
│   Mantén A 1,5 s   ▓▓▓▓▓░░░░░░                   │
└──────────────────────────────────────────────────┘
```

- El **radar** es un círculo con anillos, una barra que barre y el nivel de
  riesgo dentro.
- El **nivel** se muestra como `1/4` … `4/4`.
- La **lista de motivos** usa frases cortas, no nombres técnicos.
- El **comando exacto** sigue visible, pero en segundo plano.
- La **barra de mantener A** se llena mientras el usuario mantiene pulsado.
- El **tiempo restante** para responder está en la esquina superior derecha.
- La **cola** indica cuántos permisos más hay esperando.

Para riesgo normal o bajo, la hoja es compacta y no bloquea el dashboard. Para
riesgo alto o crítico, la hoja ocupa casi toda la pantalla y el borde cambia de
color.

---

## 3. Niveles de riesgo

| Nivel | Etiqueta | Color | Radar | Mantener A | Cuándo |
|---|---|---|---|---|---|
| 1/4 | Lectura | Verde | Estático | 0 s | `ls`, `cat`, `git status` |
| 2/4 | Normal | Azul | Estático | 0 s | Comando no reconocido o cambio normal |
| 3/4 | Alto | Ámbar | Barrido lento | 1,5 s | Borrado recursivo, force push, sudo |
| 4/4 | Crítico | Rojo | Barrido rápido + pulso | 2,5 s | `rm -rf /`, `mkfs`, `format`, `dd` |

Reglas:

- Ante la duda, se sube de nivel, nunca se baja.
- Un comando desconocido es **normal**, no bajo.
- Si coincide más de una regla, manda la más alta y se muestran todos los
  motivos.
- El color nunca va solo: siempre hay texto (`ALTO`, `3/4`) y un icono.

---

## 4. Frases de los motivos

Las reglas actuales ya devuelven motivos cortos (`borrado recursivo`,
`force push`). Añadimos una segunda capa con frases para humanos.

| Señal técnica | Frase para el usuario |
|---|---|
| borrado recursivo | Borra archivos y carpetas de forma recursiva. |
| borrado del sistema de ficheros | Borra el sistema de archivos. |
| borrado de ficheros no versionados | Borra archivos que no están en Git. |
| descarte de cambios locales | Descarta cambios que no has guardado. |
| force push | Reescribe el historial remoto y puede afectar a otros. |
| ejecución con privilegios | Ejecuta con permisos de administrador. |
| permisos abiertos | Da permisos de escritura a cualquiera. |
| ejecución de script remoto | Ejecuta código descargado de internet sin revisarlo. |
| publicación de paquete | Publica un paquete; puede ser irreversible. |
| dependencia remota sin verificar | Instala una dependencia de una URL no verificada. |
| borrado de tabla | Borra una tabla y todos sus datos. |
| borrado en Windows | Borra archivos forzando aunque estén en uso. |
| cambio del sistema en Windows | Cambia permisos o claves del sistema. |
| formateo de disco | Formatea una unidad. |
| escritura directa sobre dispositivo | Escribe directamente sobre un disco. |
| apagado del equipo | Apaga o reinicia el equipo. |
| fork bomb | Bloquea el equipo. |
| gestión de discos | Modifica las particiones del disco. |
| lectura | Solo consulta información. |
| comando no reconocido | No se reconoce como peligroso, pero puede modificar cosas. |

Si hay más de tres motivos, se muestran los tres más graves y `+N más`.

---

## 5. Cambios en el backend

### 5.1. Clasificador

`gateway/baton/risk.py`:

- `RiskAssessment` añade `details: list[str]`.
- Cada regla pasa de `(patrón, riesgo, motivo)` a
  `(patrón, riesgo, motivo, detalle)`.
- `classify()` devuelve `reasons` (técnicos) y `details` (humanos).
- Se añade `summary` derivado del nivel:
  - `low`: «Solo consulta información.»
  - `normal`: «No se reconoce como peligroso, pero puede modificar cosas.»
  - `high`: «Puede borrar o cambiar cosas importantes.»
  - `critical`: «Puede destruir datos o el sistema.»

### 5.2. Mensaje de aprobación

`protocol.py`:

- `ApprovalRequestMessage` añade `details: list[str] = []`.
- `AgentView` añade `risk_reasons: list[str]` y `risk_details: list[str]`.
- `Approval` del broker guarda `details`.

### 5.3. Estado

`state.py`:

- `AgentRuntime` guarda `risk_reasons` y `risk_details`.
- `attach_approval()` los recibe.
- `clear_approval()` los limpia.
- `view()` los expone.

### 5.4. Supervisor y adaptadores

- `supervisor.raise_approval()` pasa `details`.
- `fake.py` y `opencode.py` envían `assessment.details` al crear la aprobación.

### 5.5. Auditoría

`approvals` añade una columna `risk_details TEXT` con un JSON de frases.

- Migración segura: `ALTER TABLE ... ADD COLUMN` si no existe.
- `record_approval()` guarda `details`.
- `recent_approvals()` los devuelve.
- La app muestra los motivos en la fila de auditoría.

### 5.6. API

- `GET /api/state` ya incluye los agentes; ahora con `risk_reasons` y
  `risk_details`.
- `GET /api/audit` incluye `risk_details` en cada aprobación.
- No se añaden endpoints de decisión desde la app.

---

## 6. Cambios en el panel

### 6.1. HTML

Dentro de `#tray`:

- Un bloque `.tray-main` con:
  - `.radar` (círculo, anillos, barrido, etiqueta de nivel).
  - `.tray-info` (título, comando, cwd).
- Una lista `.tray-reasons` con un `<li>` por motivo.
- La barra de mantener A se sustituye por un **anillo** alrededor del radar
  (SVG) y se conserva una barra fina debajo como refuerzo.

### 6.2. CSS

- `.tray[data-risk="low"]` → verde.
- `.tray[data-risk="normal"]` → azul.
- `.tray[data-risk="high"]` → ámbar, borde superior y radar con barrido.
- `.tray[data-risk="critical"]` → rojo, pulso lento, barrido rápido.
- `.radar` con `conic-gradient` y un pseudo-elemento giratorio.
- `.radar-ring` SVG con `stroke-dasharray` para el progreso de A.
- Para `prefers-reduced-motion`, el barrido se desactiva.

### 6.3. JavaScript

`renderTray()`:

- Pinta `approval.details` en la lista; si no hay, usa `reasons`.
- Pinta el nivel `1/4` … `4/4` según `approval.risk`.
- Ajusta el tiempo de mantener según `approval.hold_ms`.
- Actualiza el anillo con el progreso del hold.
- Mantiene la cola y la cuenta atrás actuales.

`updateHint()`:

- «Mantén A 1,5 s para permitir» para alto.
- «Mantén A 2,5 s para permitir» para crítico.
- «A permitir · B denegar» para normal/bajo.

### 6.4. Demo

Añadir tres botones de desarrollo:

- **Permiso normal** → `npm test -- --coverage`.
- **Permiso alto** → `git clean -fdx`.
- **Permiso crítico** → `shutdown /s /t 0` o `rm -rf /` (solo se muestra; el
  agente falso no ejecuta nada).

El botón crítico permite enseñar el radar rojo en una demo de 10 segundos.

---

## 7. Cambios en la app (solo consulta)

- La tarjeta del agente muestra una insignia **«permiso»** cuando hay una
  aprobación pendiente.
- El detalle muestra:
  - Nivel de riesgo.
  - Comando.
  - Lista de motivos.
  - Aviso: **«Resuélvelo en el dispositivo»**.
- **Sin botones de permitir ni denegar.**
- Auditoría muestra el riesgo y los motivos de cada permiso.

---

## 8. Pruebas

### Unitarias

- Cada regla devuelve el nivel esperado y al menos un detalle.
- `git clean -fdx` → alto + «Borra archivos que no están en Git».
- `rm -rf /` → crítico + «Borra el sistema de archivos».
- Comando desconocido → normal + «No se reconoce como peligroso…».
- Varias reglas → nivel máximo y motivos combinados.
- `hold_ms_for`: 0, 0, 1500, 2500.

### API y estado

- `GET /api/state` incluye `risk_reasons` y `risk_details` cuando hay permiso.
- El mensaje `approval_request` incluye `details`.
- `GET /api/audit` devuelve `risk_details`.
- Al resolver o caducar, el estado limpia los motivos.

### Panel

- Aprobación normal: radar azul, 2/4, sin mantener.
- Aprobación alta: radar ámbar, 3/4, mantener 1,5 s.
- Aprobación crítica: radar rojo, 4/4, mantener 2,5 s, pulso.
- B deniega sin mantener.
- El anillo se llena y se reinicia al soltar.
- Cola y cuenta atrás siguen funcionando.

### App

- La tarjeta muestra «permiso».
- El detalle muestra los motivos y el aviso de resolver en el dispositivo.
- No hay botones de decisión.
- Auditoría muestra los motivos.

---

## 9. Criterios de aceptación

1. Un permiso alto se entiende sin saber qué hace el comando.
2. El usuario ve el nivel, el motivo y el tiempo que debe mantener A.
3. Las decisiones solo se pueden tomar en el dispositivo.
4. La app informa, pero no decide.
5. La auditoría conserva el nivel y los motivos.
6. Funciona con `prefers-reduced-motion`.
7. No se rompen los permisos existentes de OpenCode.

---

## 10. Fuera de alcance

- Explicar el comando con un modelo de lenguaje.
- Aprobar desde la app.
- Reglas automáticas que decidan sin el dispositivo.
- Analizar el contenido de los archivos que se van a modificar.
- Estimar el impacto real en el repositorio.

---

## 11. Orden de implementación

1. Clasificador con `details` y pruebas.
2. Protocolo, estado, supervisor y auditoría.
3. Panel: radar, motivos y anillo.
4. App: insignia, detalle y auditoría en modo consulta.
5. Botones de demo y prueba visual.
6. Documentación y captura para enseñar la feature.
