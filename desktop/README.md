<p align="center">
  <img src="../logos/final/png/mark-on-dark-1024.png" width="104" alt="batonAI">
</p>

# batonAI — app de escritorio

Centro de control de batonAI. Primera rebanada: elegir qué agentes se muestran
en el hardware.

## Requisitos

- Gateway en marcha (por defecto en `http://127.0.0.1:8770`).
- Python 3.11+ (probado con 3.14 y pywebview 6.2).

## Arrancar

```powershell
cd desktop
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m baton_desktop
```

Opciones:

```powershell
.\.venv\Scripts\python.exe -m baton_desktop --gateway-url http://127.0.0.1:8770
.\.venv\Scripts\python.exe -m baton_desktop --debug
```

La app **no arranca el gateway**: es un cliente. Si el gateway está caído, la app
lo indica y permite recargar.

## Estado actual

- La lista de agentes sale de `GET /api/state` del gateway y se refresca en
  silencio cada 10 s: las sesiones nuevas aparecen solas y las cerradas
  desaparecen.
- El gateway detecta **OpenCode, Claude Code, Codex, Gemini CLI, Antigravity,
  GitHub Copilot y Cursor** y las publica con ids `<proveedor>:<sesión>`.
- Cada tarjeta muestra logo, nombre del agente, modelo, proveedor, estado,
  proyecto, tarea, un **PIN** y un ojo. Hay distintivos para Anthropic/Claude,
  OpenAI/Codex, Google/Gemini, Antigravity, OpenCode, GitHub Copilot y Cursor.
- La tarjeta abre un **detalle** con ruta, coste, tokens, última salida y
  acciones: interrumpir, enviar mensaje, fijar, ocultar, abrir carpeta y copiar
  ID. La barra superior permite buscar, filtrar y ordenar, además de acciones
  masivas y avisos flotantes.
- El **PIN** fija un agente para que aparezca arriba en el hardware. Máximo dos;
  un tercero muestra un aviso. Los fijados se guardan en el gateway
  (`agent_pins`, `PATCH /api/config/pins/{id}`) y el panel los ordena primero.
- Solo aparecen agentes que tengan una sesión local reconocible; una app abierta
  sin sesiones no se inventa. En OpenCode se muestran solo las **pestañas
  abiertas**: al cerrarlas, sus agentes desaparecen en el siguiente refresco.
- El **PTT** y las **aprobaciones** se usan en el panel 480×320; esta app sigue
  siendo el centro de configuración de visibilidad.
- Los agentes ocultos bajan la opacidad y el ojo se cierra. Un fijado oculto no
  se muestra en el hardware.
- La visibilidad se guarda en el gateway (`agent_visibility`, `PATCH /api/config/visibility/{id}`)
  y la aplican el panel y el dispositivo. El puente ya no guarda una copia local.
- Sin pywebview (por ejemplo, abriendo `ui/index.html` en un navegador) usa seis
  agentes de ejemplo para revisar el diseño.

## Secciones

- **Agentes:** búsqueda, filtro por estado y proveedor, orden por estado, nombre,
  reciente o proyecto, y acciones masivas (mostrar, ocultar, limpiar fijados).
  Cada tarjeta muestra estado, proyecto, tarea, modelo, PIN y ojo. Al pulsarla se
  abre un detalle con ruta, coste, tokens, última salida y acciones: interrumpir,
  enviar mensaje, fijar, ocultar, abrir carpeta y copiar ID.
- **Hardware:** dispositivo virtual con QR TOTP, código del panel, URL del
  panel con botón para abrirlo y lista de dispositivos (`/api/devices`) con
  estado conectado/desconectado y botón de revocar
  (`POST /api/devices/{id}/revoke`).
- **Auditoría:** aprobaciones y eventos recientes (`/api/audit`).
- **Ajustes:** versión y estado del gateway, fuentes de descubrimiento, ritmos
  de sondeo (`/api/info`) y **límites reales de las IAs instaladas**. La
  configuración se cambia en el gateway con variables `BATON_*`. Incluye **Modo
  reposo**, que se puede cambiar desde la app: minutos sin actividad antes de
  atenuar el panel (0 lo desactiva).

## Panel: límites y radar

El panel 480×320 tiene una **columna de límites** dedicada. El gateway agrega
las fuentes en `/api/limits`:

- **OpenCode:** `/api/experimental/usage/limits` de su servidor local.
- **Codex:** `account/rateLimits/read` de su app-server.
- **Claude Code:** `/api/oauth/usage` con el token de `~/.claude`.

La columna lateral del dispositivo está dividida en dos mitades: arriba los
límites y abajo los estados de los agentes. Cada fila de límite muestra la IA,
la ventana, un porcentaje grande, la barra y la renovación; el color pasa de
verde a ámbar y rojo según el margen. La mitad de agentes muestra trabajando,
esperando, en espera y error, con el número grande y resaltado cuando hay
agentes en ese estado.

En **Ajustes → Límites de las IAs** se ven las IAs detectadas, su plan y todas
sus ventanas. Cada ventana tiene un **ojo**:

- ojo abierto: aparece en el dispositivo;
- ojo tachado: se oculta.

También hay un selector **Mostrar: Restante / Gastado** para que el dispositivo
enseñe lo que queda o lo consumido. Una previsualización `CINTA` resume cuántas
ventanas y de qué IAs se verán.

Si una IA no está instalada, no aparece. Si está instalada pero sin sesión, se
muestra en Ajustes con su estado, pero no ensucia la columna de límites. La
sección de límites por agente del detalle ya no existe: la fuente de verdad son
los planes reales de cada IA, no presupuestos manuales.

## Control desde otro PC

En **Ajustes → Conexión** la app puede vincularse con Google Authenticator:

1. En el dispositivo, escanea el QR con Google Authenticator.
2. En el otro PC, pulsa **Buscar dispositivo**. La app descubre el gateway en
   la red local.
3. Escribe el código de 6 dígitos y pulsa **Vincular**.

No hay que copiar URL ni token. La app guarda la conexión en
`%LOCALAPPDATA%\batonAI\control.json`; **Usar este PC** vuelve al gateway local.
La conexión manual con URL/token queda disponible en **Avanzado**.

Cuando un agente pide permiso, la hoja de aprobación muestra un **radar de
peligro** con nivel `1/4`–`4/4`, color y motivos en lenguaje normal. Para riesgo
alto hay que mantener **A** 1,5 s; para crítico, 2,5 s. La app solo lo muestra
en modo consulta: **no se aprueba desde la app**.

## Modo reposo

El panel 480×320 entra en reposo tras 5 minutos sin actividad (configurable).
Muestra la hora y el estado mínimo de los agentes; mientras tanto sigue
recibiendo el estado. Al tocar cualquier control aparece un resumen de lo que ha
pasado: terminados, esperando, errores, desconectados, permisos y coste.

- `?rest=10` en la URL del panel entra en reposo a los 10 segundos.
- `?rest=0` lo desactiva.
- El botón **modo reposo** de las herramientas, junto a **auditoría**, entra en
  reposo; al pulsarlo otra vez muestra el resumen y luego vuelve al dashboard.
- Si llega un permiso mientras está en reposo, el panel muestra «1 permiso
  pendiente» sin salir del reposo; al volver, el resumen lo destaca y **A** lleva
  a la aprobación.

Atajos: `/` enfoca la búsqueda, `Esc` cierra el detalle y `R` recarga. Los
agentes visibles avisan con un toast cuando pasan a esperar respuesta, terminan
o entran en error.

## Probar el QR TOTP (sin hardware)

El gateway incluye un **dispositivo virtual** que genera un QR real y verifica
códigos TOTP. El QR se muestra en la **pantalla del panel 480×320**, como lo
hará el ESP32; la app solo introduce el código.

1. Arranca el gateway y la app.
2. Abre **Hardware** en la app y pulsa **Abrir panel** (o ve a
   <http://127.0.0.1:8770/>). La pantalla del dispositivo muestra el QR.
3. Abre Google Authenticator (o Authy, 1Password, etc.) y añade una cuenta
   escaneando ese QR. Aparecerá como `batonAI:baton-XXXXXXXX`.
4. En la app, escribe el código de 6 dígitos y pulsa **Emparejar**.
5. La primera vez, el panel muestra «¿Emparejar con <tu PC>?» y un SAS. Pulsa
   **A** en el propio panel.
6. El panel se conecta solo y pasa al dashboard; la app muestra el dispositivo
   como emparejado.
7. Para probar un reemplazo: **Desemparejar** en la app, vuelve a introducir el
   código y confirma con A. El panel cambia de PC sin volver a escanear el QR.
8. **Nuevo QR** genera un `device_id` y un secreto nuevos. Hay que borrar la
   cuenta vieja del Authenticator y escanear el QR nuevo.

Si no puedes escanear, marca **ver código (dev)** en la app para ver el código
actual y comprobar que cambia cada 30 s. El endpoint equivalente es
`GET /api/dev/virtual` (solo loopback y con `BATON_DEV_MODE`).
