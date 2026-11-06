# Límites de las IAs en el panel

El panel de 480×320 tiene una **columna de límites** dedicada. Muestra solo las
ventanas que el usuario ha activado con el ojo en la app. No mezcla estados,
tareas, coste ni tokens con los límites.

---

## 1. Qué muestra el dispositivo

La pantalla se divide en tres zonas:

```
┌ baton.  PANEL DE CONTROL            14:05 ┐
│ ┌──────────────┐ ┌──────────────┐ ┌ Límites ─────────┐
│ │ agente       │ │ agente       │ │ OpenCode Rolling 86% │
│ │              │ │              │ │ ████████████████░░   │
│ └──────────────┘ └──────────────┘ │ restante · ↻ 9 min   │
│ ┌──────────────┐ ┌──────────────┐ │ OpenCode Semanal 86% │
│ │              │ │              │ │ ...                  │
│ └──────────────┘ └──────────────┘ ├──────────────────────┤
│ ┌──────────────┐ ┌──────────────┐ │ Agentes        1 agente │
│ │              │ │              │ │ 1 trabajando 0 esperando │
│ └──────────────┘ └──────────────┘ │ 0 en espera  0 error     │
│                                   │ coste · tok · conexión   │
└───────────────────────────────────┴──────────────────────┘
```

La columna lateral está dividida **mitad y mitad**: límites arriba y estados
de agentes abajo.

Cada fila de límite muestra:

- punto de color de la IA,
- nombre de la IA y ventana (Rolling, Semanal, Mensual),
- porcentaje grande de **restante** o **gastado**,
- barra de progreso,
- etiqueta `restante`/`usado`,
- tiempo de renovación con `↻`.

Si no hay ventanas activas: «Sin límites seleccionados. Actívalos con el ojo en
Ajustes.»

---

## 2. Selección de ventanas

En **Ajustes → Límites de las IAs** cada ventana tiene un **ojo**:

- ojo abierto: la ventana aparece en el dispositivo;
- ojo tachado: la ventana se oculta del dispositivo.

Se guarda como `ticker_windows`:

- `null` → todas las ventanas disponibles.
- Lista vacía (`[]`) → ninguna.
- Lista de claves (`["opencode:rolling","codex:monthly"]`) → solo esas.

Cada ventana tiene una clave estable con el formato `proveedor:ventana`, por
ejemplo `opencode:rolling` o `codex:monthly`.

La tarjeta de Ajustes muestra todas las IAs detectadas y todas sus ventanas,
aunque estén ocultas. La previsualización `CINTA` indica cuántas ventanas y de
qué IAs aparecerán en el dispositivo.

---

## 3. Restante o gastado

En **Ajustes → Límites de las IAs → Mostrar** se elige:

- **Restante**: el dispositivo muestra lo que queda (`87% restante`).
- **Gastado**: el dispositivo muestra lo consumido (`13% usado`).

Se guarda en `limits_view` (`remaining` o `used`). El color sigue dependiendo
del margen restante:

- verde: más del 50 % disponible,
- ámbar: entre el 21 % y el 50 %,
- rojo: 20 % o menos.

Así, en modo gastado un 90 % usado se ve en rojo, y un 10 % usado en verde.

---

## 4. Fuentes de límites

### OpenCode

`GET /api/experimental/usage/limits` del servidor local. Devuelve
`go.rolling`, `go.weekly` y `go.monthly` con `percent`, `limited` y `resetsAt`,
más presupuestos de Console.

### Codex

`account/rateLimits/read` del app-server local. Las ventanas salen de
`rateLimits.primary` y `rateLimits.secondary`, clasificadas por duración.
`individualLimit` se expone como control de gasto, no como ventana mensual.

### Claude Code

`/api/oauth/usage` con el token de `~/.claude/.credentials.json` o
`CLAUDE_CODE_OAUTH_TOKEN`. Normaliza `five_hour` como Rolling y `seven_day`
como Semanal.

### Otras IAs

Gemini, Antigravity, Cursor o Copilot no exponen una API local de cuotas en este
equipo. Se pueden añadir como nuevas fuentes cuando exista una.

---

## 5. API

- `GET /api/limits` → límites de todas las fuentes, claves de ventana, selección
  y modo de visualización.
- `PATCH /api/config/limits` → cambia `windows`, `view`, `providers` o `period`.
- `GET /api/codex/limits` → compatibilidad: solo la parte de Codex.
- `GET /api/info` incluye `ticker_windows` y `limits_view`.

Cada ventana incluye:

```json
{
  "key": "opencode:rolling",
  "id": "rolling",
  "label": "Rolling",
  "used_percent": 13,
  "remaining_percent": 87,
  "selected": true,
  "resets_at": 1793970897,
  "duration_minutes": 300
}
```

Caché:

- OpenCode y Claude: `LIMITS_POLL_S` (60 s por defecto).
- Codex: `CODEX_USAGE_POLL_S` (120 s por defecto).

---

## 6. Aspecto del dispositivo

- Cabecera de 24 px con `baton.`, «panel de control» y reloj.
- Rejilla de agentes de 2 columnas y 3 filas visibles.
- Columna derecha de 160 px dividida en dos mitades:
  - arriba, límites de las ventanas activas;
  - abajo, estados de agentes (trabajando, esperando, en espera, error).
- Cada límite tiene color de IA, porcentaje grande, barra y renovación.
- Cada estado muestra un número grande y se ilumina cuando hay agentes en él.
- El pie de la mitad de agentes muestra coste, tokens y conexión.

---

## 7. Pruebas

- Ojos por ventana: activar y ocultar.
- Atajo «todas»: `ticker_windows = null`.
- Modo restante y modo gastado.
- OpenCode con Rolling/Semanal/Mensual.
- Codex con plan free (solo mensual).
- Claude con `five_hour` y `seven_day`.
- IA no instalada: no aparece.
- IA instalada sin sesión: no rompe el panel.
- El dispositivo solo muestra las ventanas con ojo abierto.
