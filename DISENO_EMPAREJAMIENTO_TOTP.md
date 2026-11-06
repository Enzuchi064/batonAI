# Emparejamiento TOTP de batonAI

Diseño del flujo «el dispositivo muestra un QR, Google Authenticator genera el
código y la app lo introduce para emparejarlo». Sustituye, para el hardware, al
código de 6 dígitos que hoy imprime el gateway.

> Estado: **F0 implementado** (TOTP, dispositivo virtual y asistente en la app).
> El panel web sigue usando el código actual como simulador. Falta el firmware
> real y el transporte USB/LAN del dispositivo.

---

## 1. Decisiones de partida

| Decisión | Valor |
|---|---|
| Factor de emparejamiento | TOTP (Google Authenticator u otra app compatible) |
| Quién muestra el secreto | El dispositivo, en un QR `otpauth://` |
| Quién verifica el código | El dispositivo, nunca el gateway |
| Quién introduce el código | La app de escritorio |
| PCs recordados | **Uno a la vez**; otro PC exige volver a emparejar |
| Primer arranque | QR visible sin configuración previa |
| Transporte de emparejamiento | USB CDC **y** LAN (mDNS + HTTPS), mismo protocolo |
| Transporte de trabajo | Wi-Fi + WebSocket contra el gateway |
| Secreto TOTP | Persistente entre emparejamientos |
| Confirmación física | Obligatoria la **primera** vez; los reemplazos solo piden código |
| Alcance | LAN; internet queda fuera de v1 |

---

## 2. Lo que TOTP hace y lo que no

TOTP demuestra **posesión de un secreto y un reloj**. No descubre el dispositivo,
no lo identifica y no cifra nada. El QR contiene el secreto en claro: quien lo
fotografíe puede añadirlo a su Authenticator.

Por eso el diseño no usa TOTP como única prueba. El **primer** emparejamiento
exige tres cosas a la vez:

1. **Posesión física del dispositivo** (ver el QR en su pantalla y pulsar A).
2. **Posesión del Authenticator** (el código de 6 dígitos).
3. **Un PC concreto** (la app inicia la sesión y el dispositivo muestra su
   nombre antes de aceptar).

Los reemplazos bajan a dos: una ventana de emparejamiento abierta físicamente
(USB, reinicio o `A+B`) y el código del Authenticator.

El QR solo se muestra en modo emparejamiento, nunca en el panel de trabajo. El
QR caduca a los 120 s y la ventana se cierra antes si el emparejamiento termina.

### Primera vez frente a reemplazo

| | Primera vez | Reemplazo en otro PC |
|---|---|---|
| Ventana de emparejamiento | Automática al arrancar | Al enchufar USB, al arrancar sin gateway o con `A+B` |
| Código TOTP | Sí | Sí |
| Confirmar con A | **Sí** | **No**; banner de 5 s y B para cancelar |
| Secreto TOTP | Se conserva | Se conserva |

El reemplazo sin A es una decisión de comodidad: el código del Authenticator y
el acceso a la ventana de emparejamiento (USB o reinicio) hacen de prueba. Si
más adelante se quiere endurecer, `require_confirm_always` vuelve a pedir A en
cada emparejamiento.

---

## 3. Visión general

Los papeles se invierten durante el emparejamiento:

- **Dispositivo:** servidor de emparejamiento. Guarda el secreto TOTP, verifica
  el código y decide a qué PC se ata.
- **App:** cliente de emparejamiento. Habla con el dispositivo por USB y con el
  gateway por loopback.
- **Gateway:** servidor de trabajo. Emite el token, guarda el dispositivo y
  atiende el WebSocket cuando el emparejamiento termina.

Después del emparejamiento, el dispositivo vuelve a ser cliente del gateway.

```
Authenticator          Dispositivo                 App (PC)                Gateway
     |                      |                          |                       |
     |  (1) QR otpauth      |                          |                       |
     |<---------------------|                          |                       |
     |  (2) código 6 díg.   |                          |                       |
     |                      |<---(3) pair_request------|                       |
     |                      |---(4) verifica TOTP       |                       |
     |                      |---(5) muestra PC + SAS    |                       |
     |                      |    [A] confirma            |                       |
     |                      |---(6) pair_accepted------>|                       |
     |                      |                          |--(7) /api/pair/complete-->|
     |                      |                          |<--(8) device_token-------|
     |                      |<---(9) pair_finish-------|                       |
     |                      |---(10) WebSocket + token------------------------->|
```

La sesión del gateway (paso 7) se crea **antes** del paso 3; aquí se omite para
no cargar el diagrama. El `nonce` de esa sesión viaja al dispositivo y vuelve
firmado o referenciado en la respuesta.

---

## 4. Estados del dispositivo

| Estado | Qué muestra | Sale a |
|---|---|---|
| `BOOT` | Logo | `WIFI_SETUP`, `PAIRING` o `CONNECTING` |
| `WIFI_SETUP` | SSID `baton-XXXX` y `http://192.168.4.1` | `PAIRING` |
| `PAIRING` | QR + id corto + cuenta atrás 120 s | `VERIFYING`, `IDLE` |
| `VERIFYING` | «Comprobando código…» | `CONFIRM`, `PAIRING` |
| `CONFIRM` | «¿Emparejar con DESKTOP-X?» + SAS + A/B, 30 s | `EXCHANGE`, `PAIRING` |
| `CONFIRM_REPLACE` | «Reemplazar DESKTOP-A por DESKTOP-B» 5 s + B, sin A | `EXCHANGE`, `PAIRING` |
| `EXCHANGE` | «Esperando al PC…», 60 s | `CONNECTING`, `PAIRING` |
| `CONNECTING` | «Conectando con el gateway…» | `ONLINE`, `PAIRING` |
| `ONLINE` | Panel normal | `PAIRING` si se desempareja |
| `IDLE` | «Mantén A+B para emparejar» | `PAIRING` |

Reglas:

- Sin emparejamiento previo, el primer arranque entra en `PAIRING` solo.
- Con emparejamiento previo, arranca en `CONNECTING`.
- La ventana de emparejamiento se abre sola al enchufar el USB, al arrancar sin
  gateway alcanzable, y con `A+B` durante 3 s en cualquier estado.
- `A+B` pide confirmación en pantalla para no abrirlo por accidente.
- En el primer emparejamiento, la confirmación con A es obligatoria.
- En un reemplazo, tras validar el código se muestra `CONFIRM_REPLACE` durante
  5 s; B cancela y cualquier otra tecla lo acepta.
- Salir de `PAIRING` borra el QR y el secreto temporal de la pantalla.
- Un fallo de código no cierra la ventana: vuelve a `PAIRING` y suma un intento.

---

## 5. Primer arranque, paso a paso

1. El dispositivo crea `device_id` (`baton-` + 8 hex) la primera vez y lo guarda
   en NVS. No cambia nunca salvo borrado de fábrica.
2. Entra en `PAIRING` y genera un secreto TOTP de 20 bytes.
3. Pinta el QR y el id corto (`BATON-3F2A9C`) con una cuenta atrás de 120 s.
4. El usuario escanea el QR con Google Authenticator. La entrada queda como
   `batonAI:baton-3f2a9c`.
5. Conecta el dispositivo al PC por USB (datos, no solo carga) o lo deja en la
   misma Wi-Fi. El USB es la vía recomendada; la LAN sirve cuando el cable es
   solo de alimentación.
6. Abre la app → **Hardware** → **Emparejar dispositivo**. La app busca por USB
   y por mDNS, y muestra el dispositivo detectado.
7. El usuario escribe el código de 6 dígitos y pulsa **Emparejar**.
8. La app crea la sesión en el gateway y envía `pair_request` al dispositivo.
9. El dispositivo verifica el código, muestra el nombre del PC y un **SAS** de 4
   dígitos; el usuario compara que coincide con el de la app y pulsa **A**.
   (En un reemplazo no se pulsa A: basta el código y el aviso de 5 s.)
10. El dispositivo responde `pair_accepted`; la app registra el dispositivo en el
    gateway y recibe `device_token`; se lo envía en `pair_finish`.
11. El dispositivo guarda el único emparejamiento, borra el secreto de la RAM de
    trabajo (sigue en NVS), muestra «Emparejado con DESKTOP-X» y conecta el
    WebSocket.
12. El gateway marca el dispositivo como conectado y la app lo lista en
    **Hardware**.

Si algo falla antes del paso 11, el dispositivo no guarda nada y vuelve a
`PAIRING`; el gateway invalida la sesión a los 120 s.

---

## 6. El QR

Formato estándar para que lo entienda cualquier app de autenticación:

```
otpauth://totp/batonAI%3Abaton-3f2a9c
  ?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP
  &issuer=batonAI
  &algorithm=SHA1
  &digits=6
  &period=30
```

- Etiqueta: `batonAI:<device_id>`. Así se pueden tener varios batones en la
  misma app.
- Secreto: 160 bits en base32, generado con un CSPRNG del ESP32.
- El QR ocupa 200×200 px como máximo en la pantalla de 480×320; debajo van el id
  corto y la cuenta atrás.
- **No** se muestra el secreto en texto ni se escribe en logs.
- El QR solo existe en `PAIRING`. Al salir se borra el buffer y, si el secreto
  era nuevo, se descarta.

### Ciclo de vida del secreto

Decidido: **persistir el secreto** entre emparejamientos. El usuario escanea
una vez y el mismo código le sirve para emparejar el dispositivo en otro PC más
adelante. Es lo que encaja con «en cualquier PC que lo pongas».

Contrapartida: quien tenga el Authenticator y acceso físico al dispositivo puede
volver a emparejarlo. Se mitiga con:

- modo emparejamiento solo tras una acción física (USB, reinicio o `A+B`);
- confirmación A la primera vez y `require_confirm_always` si se quiere siempre;
- ventana corta y límite de intentos;
- opción «rotar secreto» que genera un QR nuevo tras cada emparejamiento;
- borrado de fábrica que invalida el Authenticator anterior.

Alternativa más estricta: rotar el secreto en **cada** emparejamiento. Más
seguro, pero obliga a borrar y volver a escanear el QR cada vez. No es el
comportamiento por defecto; se puede activar con `pair_rotate`.

---

## 7. Transporte de emparejamiento

Se soportan **los dos canales** con el mismo protocolo. La app intenta USB
primero y, si no hay cable de datos, busca por mDNS. El dispositivo no distingue
el contenido: solo cambia el transporte.

### 7.1. USB CDC / puerto serie (vía principal)

- El ESP32-S3 expone un CDC ACM (o un chip USB-serie en las placas de
  desarrollo). La app lo ve como `COMx`.
- La app enumera puertos, envía `pair_hello` y se queda con el que responde con
  el protocolo de batonAI.
- Ventajas: no depende de Wi-Fi, no hay descubrimiento ni TLS, funciona en
  cualquier PC al enchufar, y el canal físico es la prueba de proximidad.
- El mismo canal sirve para enviar la hora del PC y, opcionalmente, las
  credenciales Wi-Fi.
- Enchufar el USB abre la ventana de emparejamiento sin tocar botones.

### 7.2. LAN con mDNS + HTTPS

- mDNS `_batonai._tcp` con TXT `id`, `pair=1`, `proto=1`, `fp=<huella>`.
- El dispositivo levanta un servidor de emparejamiento efímero (120 s) en
  `https://<ip>:8443` con certificado autofirmado.
- La pantalla muestra una **huella corta** de 6 hex junto al QR; la app muestra
  la que anuncia mDNS. El usuario las compara la primera vez.
- El código viaja por TLS (certificado autofirmado y huella fijada). Para un
  endurecimiento mayor, ECDH efímero en F3.
- Útil si el cable es solo de carga o el dispositivo está lejos del PC.
- La ventana se abre al arrancar sin gateway alcanzable o con `A+B`. Si el
  dispositivo está online con el PC anterior, un reemplazo por LAN exige `A+B`.

### 7.3. Cuándo se abre la ventana

| Situación | ¿Se abre sola? |
|---|---|
| Primer arranque | Sí, 120 s |
| USB enchufado a un PC | Sí, 120 s |
| Arranque sin gateway alcanzable | Sí, 5 min |
| `A+B` 3 s | Sí, 120 s |
| Online con un PC y otro PC por LAN | No; hace falta `A+B` |

### 7.4. Descartado por ahora

- **BLE:** soporte irregular en Windows y más superficie de ataque.
- **Cámara en la app:** obligaría a leer el QR `otpauth`, que no lleva la
  identidad del dispositivo ni la huella TLS. El USB y mDNS ya dan esa
  información.
- **nube/relay:** fuera de alcance; «cualquier PC» significa «cualquier PC de la
  misma LAN», no internet.

---

## 8. Protocolo de emparejamiento

JSON por líneas (`\n`), UTF-8, máximo 4 KB por mensaje. Campo `t` = tipo y
`proto` = versión. El dispositivo ignora mensajes desconocidos y cierra la
conexión si se supera el límite.

### 8.1. Mensajes

```jsonc
// dispositivo -> app, al detectarlo
{ "t": "pair_hello", "proto": 1, "device_id": "baton-3f2a9c",
  "short": "3F2A9C", "fw": "0.1.0", "pairing": true, "clock_ok": false }

// app -> dispositivo
{ "t": "pair_request", "proto": 1, "device_id": "baton-3f2a9c",
  "code": "123456", "session": "b64url-16B", "nonce": "b64url-16B",
  "gateway": { "id": "gw-7c1a2b3d", "name": "DESKTOP-ENZO",
               "url": "ws://192.168.1.20:8770" },
  "pc_time": "2026-11-05T21:40:00Z" }

// dispositivo -> app
{ "t": "pair_accepted", "device_id": "baton-3f2a9c",
  "session": "b64url-16B", "sas": "4821" }

// app -> dispositivo
{ "t": "pair_finish", "device_token": "…",
  "wifi": { "ssid": "Casa", "pass": "…" } }   // wifi opcional

// dispositivo -> app
{ "t": "pair_ok", "device_id": "baton-3f2a9c" }

// errores
{ "t": "pair_error", "code": "bad_code", "message": "código incorrecto" }
```

### 8.2. Códigos de error

| Código | Significado | Reacción de la app |
|---|---|---|
| `bad_code` | TOTP no válido | Pedir otro código |
| `expired` | Ventana o sesión caducada | Reiniciar emparejamiento |
| `rate_limited` | Demasiados intentos | Esperar 60 s |
| `busy` | Ya hay una sesión en curso | Esperar |
| `wrong_device` | `device_id` no coincide | Re-detectar |
| `bad_clock` | El dispositivo no tiene hora fiable | Enviar `pc_time` |
| `sas_mismatch` | El SAS no coincide | Abortar; posible inyección |
| `proto` | Versión incompatible | Actualizar app/firmware |

### 8.3. Sesión del gateway

`POST /api/pair/session` (solo loopback):

```json
{ "name": "Emparejar dispositivo" }
→ { "session_id": "…", "nonce": "…", "gateway_id": "gw-7c1a2b3d",
    "gateway_url": "ws://192.168.1.20:8770", "expires_at": "…" }
```

- `nonce` y `session_id`: 16 bytes aleatorios.
- Caducidad: 120 s. Una sesión usada no se puede reutilizar.
- El gateway no ve el código TOTP ni el secreto.

`POST /api/pair/complete` (solo loopback):

```json
{ "session_id": "…", "device_id": "baton-3f2a9c",
  "name": "baton de Enzo" }
→ { "device_token": "…", "gateway_id": "gw-7c1a2b3d",
    "gateway_url": "ws://192.168.1.20:8770" }
```

El gateway comprueba que la sesión existe, no ha caducado y no se ha usado;
emite un token nuevo, guarda su hash y marca la sesión como consumida. En v1 la
prueba de que el dispositivo participó es que la app (loopback, de confianza)
recibió `pair_accepted`; en v2 se añade una firma del dispositivo.

### 8.4. SAS

`SAS = SHA256(session_id || nonce || device_id)` → 4 dígitos decimales.

- La app lo calcula al crear la sesión y lo muestra.
- El dispositivo lo calcula al recibir `pair_request` y lo muestra en la
  confirmación.
- Si no coincide, el usuario pulsa B: alguien está inyectando una sesión.
- No sustituye a la ventana física; la refuerza.

---

## 9. Verificación TOTP

| Parámetro | Valor |
|---|---|
| Algoritmo | HMAC-SHA1 |
| Dígitos | 6 |
| Periodo | 30 s |
| Ventana | ±1 paso (±30 s) |
| Secreto | 20 bytes (160 bits) |
| Comparación | tiempo constante |
| Intentos fallidos | 5 → bloqueo 60 s; 10 → cerrar ventana |
| Replay | se recuerda el último `step` aceptado |
| Caducidad de la ventana | 120 s (5 min si se abre por arranque sin gateway) |
| Caducidad de la confirmación | 30 s |
| Caducidad del intercambio | 60 s |

Reglas:

- Un código aceptado **no se puede reutilizar** dentro de la misma ventana. Si
  el flujo se aborta después de aceptarlo, hay que esperar al siguiente código.
- Los intentos fallidos no consumen el código; solo suman al límite.
- El `step` aceptado se guarda en RAM. Tras un reinicio se pierde, pero la
  ventana es corta y el código sigue caducando a los 30 s.
- El código nunca se registra en auditoría; solo se anota `pair_failed` sin
  código.

### Reloj

TOTP exige hora correcta. Orden de preferencia:

1. **SNTP** tras conectar el Wi-Fi (`pool.ntp.org`, `time.cloudflare.com`).
   Si la hora es válida, `clock_ok = true`.
2. **Hora del PC** en `pair_request.pc_time`, solo si el dispositivo no tiene
   hora válida. Se acepta si está entre la fecha de compilación y 20 años
   después, y se marca `time_source = pc`.
3. Si no hay ninguna, el dispositivo muestra «Sin hora: conecta el USB» y no
   pinta el QR.

La hora del PC no se usa para el funcionamiento normal: en cuanto hay red, SNTP
manda. El gateway no participa en la verificación del código.

### Por qué verifica el dispositivo

- El secreto no sale del dispositivo; el gateway no puede (ni debe) tenerlo.
- El dispositivo es quien decide a qué PC se ata.
- Si verificara el gateway, habría que enviarle el secreto o el código por la
  red, y el dispositivo seguiría sin poder comprobar quién llama.

---

## 10. Un PC a la vez

### 10.1. Lo que guarda el dispositivo

Una sola ficha en NVS:

| Clave | Contenido |
|---|---|
| `device_id` | `baton-3f2a9c` |
| `totp_secret` | Secreto base32 (persistente) |
| `pair_gw_id` | `gw-7c1a2b3d` |
| `pair_gw_url` | `ws://192.168.1.20:8770` |
| `pair_gw_name` | `DESKTOP-ENZO` |
| `pair_token` | Token emitido por el gateway |
| `pair_at` | Fecha del emparejamiento |
| `pair_rotate` | Rotar secreto tras emparejar (0/1) |

### 10.2. Emparejar en otro PC

1. Enchufa el dispositivo al PC nuevo por USB (o pulsa `A+B` 3 s si va por LAN).
   La ventana de emparejamiento se abre sola; el QR vuelve a salir.
2. En el PC nuevo: app → Hardware → Emparejar; se detecta por USB o mDNS.
3. Código del Authenticator (el mismo de siempre, porque el secreto persiste).
4. El dispositivo muestra «Reemplazar DESKTOP-A por DESKTOP-B» durante 5 s; no
   hace falta pulsar A. B cancela.
5. Al aceptar:
   - intenta avisar al gateway anterior (`unpair`) si sigue conectado;
   - borra token, URL y nombre anteriores;
   - guarda la ficha nueva;
   - conecta al gateway nuevo.
6. El gateway nuevo emite un token nuevo. El anterior queda inútil para ese
   dispositivo porque el dispositivo ya no lo presenta.

El reemplazo sin A es deliberado: el usuario ya demostró posesión del
Authenticator y de la ventana física (USB o `A+B`). Si se quiere más rigor,
`require_confirm_always` vuelve a pedir A.

### 10.3. Qué ve el PC anterior

- Si recibió `unpair`: el dispositivo pasa a `revocado` en **Hardware**.
- Si no estaba conectado: sigue en la lista como `desconectado`. El usuario
  puede revocarlo a mano. Aunque el token viejo siguiera en la base de datos, el
  dispositivo ya no lo usa y el gateway nuevo tiene otro.
- El PC anterior no puede recuperar el dispositivo sin volver a emparejarlo
  físicamente.

### 10.4. Desemparejar

- Desde el dispositivo: menú `A+B` → «Desemparejar» → confirmar con A.
- Borra la ficha, avisa al gateway y vuelve a `PAIRING`.
- Desde la app: **Hardware → Revocar** invalida el token en ese gateway; el
  dispositivo conserva la ficha y fallará al conectar (4401), así que se borra
  la ficha y pide emparejar de nuevo.

---

## 11. Cambios en el gateway

### 11.1. Endpoints nuevos

| Ruta | Quién | Qué hace |
|---|---|---|
| `POST /api/pair/session` | loopback | Crea sesión + nonce (120 s) |
| `POST /api/pair/complete` | loopback | Valida sesión y emite token |
| `POST /api/pair/cancel` | loopback | Cancela una sesión |
| `GET /api/pair/session/{id}` | loopback | Estado (para la UI) |
| `GET /api/dev/virtual/*` | loopback + dev | Dispositivo virtual (F0) |

Se mantienen `POST /api/pair` y `GET /api/dev/pairing` para el panel web y las
pruebas actuales, marcados como **simulador**. El hardware no los usa.

### 11.2. Identidad del gateway

Tabla nueva:

```sql
CREATE TABLE IF NOT EXISTS gateway_identity (
    id         TEXT PRIMARY KEY,
    public_key TEXT,
    private_key TEXT,
    created_at TEXT NOT NULL
);
```

- `id`: `gw-` + 8 hex, generado en el primer arranque.
- En v1 solo se usa `id`. Las claves pública/privada quedan para la fase v2
  (firma del dispositivo y pinning TLS).
- La privada, si se usa, se protege con DPAPI en Windows o un archivo con
  permisos restringidos; nunca se registra.

### 11.3. Tabla `devices`

```sql
ALTER TABLE devices ADD COLUMN pubkey TEXT;
ALTER TABLE devices ADD COLUMN gateway_id TEXT;
ALTER TABLE devices ADD COLUMN paired_at TEXT;
```

`token_hash` sigue siendo el único dato del token que se guarda. `pubkey` se
rellena en v2.

### 11.4. Sesiones

En memoria (`dict` con TTL y limpieza perezosa) es suficiente: si el gateway se
reinicia a mitad de emparejamiento, la app reinicia el flujo. No hace falta
persistir nonces.

### 11.5. Auditoría

Eventos nuevos, sin secretos ni códigos:

- `pair_session_created` (`session_id` corto, nombre del PC)
- `device_paired` (ya existe)
- `device_unpaired`
- `pair_failed` (`reason`: `bad_code`, `expired`, `rate_limited`, …)

### 11.6. Auth del WebSocket

v1 mantiene el token actual. v2 añade reto-respuesta con la clave del
dispositivo para que un token copiado no baste.

---

## 12. Cambios en la app

### 12.1. Hardware

Sustituir la tarjeta «Emparejamiento» por un asistente:

1. **Detectar**: «Conecta el dispositivo por USB o déjalo en la misma Wi-Fi».
   Botón **Buscar**. La app prueba puertos (`pair_hello`) y mDNS
   (`_batonai._tcp`); si hay uno, se selecciona solo. La lista indica el
   transporte y, en LAN, la huella corta.
2. **Código**: muestra id, firmware y si el reloj está bien. Campo de 6 dígitos
   con autofoco y pegado.
3. **Confirmar (solo la primera vez)**: tras `pair_accepted`, muestra el SAS y
   «Pulsa A en el dispositivo». Cuenta atrás de 30 s.
4. **Listo**: «Emparejado con DESKTOP-X». El dispositivo aparece en la lista.
5. **Reemplazo**: si el dispositivo ya está emparejado, aviso de que se
   reemplazará el PC actual. No pide A: el dispositivo muestra el aviso de 5 s y
   la app espera el `pair_ok`.

La tarjeta actual de código de 6 dígitos pasa a una sección «Simulador» visible
solo con `BATON_DEV_MODE=1`.

### 12.2. Puente

Métodos nuevos en `bridge.py`:

- `pair_scan() -> {ok, devices: [{transport, port|host, device_id, short, fw, clock_ok}]}`
- `pair_start(transport, target, code, device_id) -> {ok, sas, session_id}`
- `pair_status(session_id) -> {ok, state}`
- `pair_cancel(session_id)`
- `virtual_device() -> {ok, qr_svg, device_id, short, code}` (solo dev)

`pair_scan` y `pair_start` usan `pyserial`; si no está instalado, la app muestra
«Instala pyserial para emparejar por USB».

### 12.3. Dispositivo virtual (F0)

Antes de tener hardware, el gateway simula el dispositivo:

- Genera `device_id`, secreto TOTP y estado `PAIRING`.
- Expone el QR como SVG (`segno`) y, solo en dev, el código actual.
- El **panel 480×320** (`/`) pinta ese QR y hace de pantalla del dispositivo:
  muestra el id, espera la confirmación y, al pulsar **A**, confirma y se
  conecta con el token.
- La app solo detecta el dispositivo e introduce el código; no muestra el QR.
- Implementa los mismos estados y mensajes que tendrá el firmware.

Así se prueba el flujo completo, la UI y los errores sin ESP32.

---

## 13. Cambios en el firmware

### 13.1. NVS

Ver §10.1. En producción, NVS cifrada con clave en eFuse. El borrado de fábrica
(`A+B+PTT` 10 s) borra todo y genera `device_id` y secreto nuevos.

### 13.2. Módulos

| Módulo | Responsabilidad |
|---|---|
| `pairing.c` | Máquina de estados y mensajes |
| `totp.c` | HMAC-SHA1, base32, ventana y replay |
| `qr.c` | QR `otpauth` (qrcodegen, MIT) |
| `serial_pair.c` | USB CDC, líneas JSON, límite de 4 KB |
| `sntp.c` | Hora de red y validez |
| `nvs_store.c` | Ficha de emparejamiento y preferencias |

### 13.3. Pantalla de emparejamiento

- QR 200×200, id corto debajo, cuenta atrás.
- Al recibir `pair_request`: si es la primera vez, pantalla de confirmación con
  nombre del PC, SAS y «A = emparejar · B = cancelar». Si es un reemplazo,
  pantalla de aviso de 5 s con «B = cancelar» y sin A.
- Al emparejar: «Emparejado con DESKTOP-X» 2 s y salto a `CONNECTING`.
- Si el código falla: «Código incorrecto» 2 s y vuelve al QR.
- Si no hay hora: «Sin hora: conecta el USB».

### 13.4. Wi-Fi

- Se mantiene el SoftAP de primer arranque.
- Opcional: `pair_finish.wifi` permite configurar SSID/contraseña desde la app
  por USB. Si llega, se guarda y se reinicia la conexión.
- Si el PC nuevo está en otra red, se reempareja por USB y se envían las nuevas
  credenciales.

---

## 14. Seguridad y amenazas

| Amenaza | Mitigación |
|---|---|
| Foto del QR | Solo en modo emparejamiento; ventana corta y A la primera vez |
| Código visto por encima del hombro | Ventana de 30 s, replay por `step`, límite de intentos |
| Reemplazo no autorizado | Hace falta una ventana física (USB/reinicio/`A+B`) y el código; opción `require_confirm_always` |
| Replay de un código | `step` aceptado no reutilizable; sesión con `nonce` |
| PC falso en la LAN | Huella TLS + SAS; el USB evita la red por completo |
| MITM en Wi-Fi | TLS con certificado del gateway y pinning (fase v2) |
| Dispositivo robado | Ficha + token revocable; borrado de fábrica inutiliza claves |
| PC robado | Token hasheado en SQLite; revocar desde la app o el dispositivo |
| Authenticator robado | Sigue haciendo falta el dispositivo y pulsar A |
| Reloj manipulado | SNTP manda; hora del PC solo si no hay red y con límites |
| Fuerza bruta | 5 intentos → 60 s; 10 → cerrar ventana |
| Logs con secretos | Nunca se registran código, secreto ni token |

El QR **es** un secreto. La pantalla no lo muestra fuera de `PAIRING` y el
firmware borra el buffer de vídeo al salir. El manual debe decirlo.

---

## 15. Pruebas

### 15.1. Unitarias

- TOTP con vectores RFC 6238 (SHA1) y base32.
- Ventana ±1, código de paso anterior y posterior.
- Replay: mismo `step` dos veces → rechazo.
- Límite de intentos y bloqueo.
- `SAS` estable y distinto por sesión.
- Sesión caducada, usada y desconocida.
- Token: hash, revocación y dispositivo desconocido.

### 15.2. Protocolo

- `pair_hello` → `pair_request` → `pair_accepted` → `pair_finish` → `pair_ok`.
- Código incorrecto, caducado, repetido y con reloj mal.
- `device_id` que no coincide.
- Mensaje > 4 KB, JSON inválido, base64 inválido.
- Reemparejamiento: la ficha anterior se sustituye y el token viejo no conecta.
- `unpair` best-effort y revocación manual.

### 15.3. Integración

- Dispositivo virtual + app: flujo feliz y errores.
- Dispositivo virtual + gateway: `welcome`, `state` y aprobaciones tras emparejar.
- USB simulado con `pyserial` (loopback) o un mock del puerto.
- Reinicio del gateway a mitad de sesión → la app reinicia el flujo.

### 15.4. Hardware

- QR legible con la cámara de un móvil en 3 s.
- 100 emparejamientos seguidos sin fugas de memoria.
- Corte de USB a mitad → el dispositivo vuelve a `PAIRING`.
- Reinicio sin red → pide USB para la hora y no pinta QR.
- Borrado de fábrica → `device_id` y secreto nuevos.

---

## 16. Fases

| Fase | Contenido | Depende de | Estado |
|---|---|---|---|
| **F0** | TOTP en Python, dispositivo virtual, endpoints, asistente en la app, pruebas | Nada | **Hecho** |
| **F1** | USB real, firmware mínimo de emparejamiento, QR en pantalla | Hardware | Pendiente |
| **F2** | LAN con mDNS + TLS pinning, reemparejamiento y revocación completa | F1 | Pendiente |
| **F3** | Wi-Fi por USB, firma del dispositivo, NVS cifrada | F2 | Pendiente |

F0 está hecho: no necesitaba hardware y valida el flujo que el usuario va a
usar. La app se diseña con un `PairingTransport` abstracto para que USB y LAN
compartan el mismo asistente. La siguiente rebanada es F1 (hardware real).

---

## 17. Decisiones

Cerradas:

| # | Pregunta | Decisión |
|---|---|---|
| 1 | ¿USB, Wi-Fi o ambos? | **Ambos**; USB primero, LAN después, mismo protocolo |
| 2 | ¿El secreto TOTP persiste? | **Sí**; rotación solo como opción manual |
| 3 | ¿Confirmación física siempre? | **Solo la primera vez**; reemplazos con código |

Abiertas:

| # | Pregunta | Recomendación |
|---|---|---|
| 4 | ¿Wi-Fi por SoftAP o por USB? | SoftAP ahora; USB opcional en F3 |
| 5 | ¿La app necesita cámara? | No en v1 |
| 6 | ¿Huella TLS en LAN o ECDH? | Huella fijada ahora; ECDH en F3 |
| 7 | ¿`require_confirm_always` por defecto? | No, según la decisión 3 |

---

## 18. Resumen

- El flujo del usuario es viable: QR en el dispositivo → Authenticator → código
  en la app → dispositivo emparejado con ese PC.
- TOTP se usa como **prueba de posesión**, no como identificador ni cifrado.
- El dispositivo es quien verifica y quien decide; el gateway solo emite el
  token cuando la app se lo pide por loopback.
- «Cualquier PC» se resuelve reemparejando: el dispositivo guarda un solo PC y
  lo reemplaza al recibir un código válido.
- La primera vez exige QR + código + A; los reemplazos exigen código y una
  ventana abierta por USB, reinicio o `A+B`.
- USB y LAN comparten protocolo. El USB resuelve descubrimiento, reloj y TLS; la
  LAN permite emparejar cuando el cable es solo de carga.
- El secreto persiste: se escanea una vez y sirve para siempre, salvo borrado de
  fábrica o rotación manual.

---

## 19. Provisión de fábrica y primer arranque

### 19.1. Qué necesita el dispositivo para pintar el QR

Solo el **firmware**. No hace falta precargar un secreto por unidad: el ESP32
puede generarlo en el primer arranque.

1. `nvs_flash_init()`.
2. Si no existe `device_id`, se generan 4 bytes con `esp_random()` y el
   `device_id` queda como `baton-XXXXXXXX`.
3. Se generan 20 bytes con `esp_fill_random()` y se codifican en base32: es el
   secreto TOTP.
4. Se guardan ambos en NVS.
5. El QR se construye en RAM desde el secreto y se pinta en pantalla. No se
   envía a ninguna nube ni hace falta el gateway.

El QR se puede generar **sin Wi-Fi y sin hora**. La hora solo hace falta para
verificar el código cuando el usuario lo introduce: la app puede mandarla por
USB y, si hay Wi-Fi, SNTP la mantiene.

### 19.2. Dos modelos

| | Generar en primer arranque | Preaprovisionar en fábrica |
|---|---|---|
| Qué se graba | Solo firmware | Firmware + identidad/secreto por unidad |
| Quién genera el secreto | TRNG del ESP32 | Estación de fábrica |
| QR impreso en la caja | No | Sí |
| Base de datos de secretos | No | Sí (riesgo) |
| Trazabilidad | `device_id` en la app | Lote/número de serie |
| Reparación o refurb | Borrado de fábrica genera uno nuevo | Hay que reasignar |
| Coste | Bajo | Alto |

Recomendación: **firmware + Secure Boot**, identidad y secreto en el primer
arranque. Si se necesita un QR impreso, se imprime desde la app tras el primer
arranque o se usa el modelo híbrido.

### 19.3. Modelo híbrido (producto)

- En fábrica: número de serie y par de claves del dispositivo en una partición
  de provisión; Secure Boot v2 y Flash Encryption.
- El secreto TOTP se genera en el primer arranque y **nunca sale** del
  dispositivo.
- La caja lleva el número de serie, no el secreto.
- El QR se ve en pantalla; si se quiere etiqueta, la app lo imprime.

### 19.4. Línea de producción

1. Flashear el binario fusionado (`bootloader`, tabla de particiones y app) con
   `esptool.py`.
2. Test de arranque: pantalla, botones, encoder, audio, Wi-Fi y generación de
   QR.
3. Test de TOTP: un fixture lee el `otpauth` por USB en modo test, calcula un
   código y comprueba que el dispositivo lo acepta. Al terminar, borrado de
   fábrica para que el cliente reciba un secreto nuevo.
4. Activar Secure Boot/Flash Encryption al final (los eFuse son irreversibles).
5. Etiquetar con el número de serie; el QR no se imprime.
6. Opcional: OTA a la última versión antes de embalar.

### 19.5. Seguridad

- Sin cifrado de flash, el secreto TOTP se puede leer con acceso físico
  (`esptool read_flash`). Para un producto: NVS cifrada + Flash Encryption.
- Secure Boot v2 impide flashear firmware no firmado.
- El QR es un secreto: no se muestra fuera de `PAIRING`, no se registra y no se
  imprime en la caja.
- El borrado de fábrica (`A+B+PTT` 10 s) borra identidad, secreto y
  emparejamiento; el Authenticator viejo deja de valer.
- Si el usuario pierde el Authenticator antes de emparejar, vuelve a escanear
  el QR. Si lo pierde después y quiere otro PC, hace falta borrado de fábrica
  (o una copia del secreto, que no recomendamos).

### 19.6. Primer arranque real

1. Power on → el firmware comprueba NVS.
2. Sin identidad → genera `device_id`, secreto y claves; los guarda.
3. Pinta QR + id + «Empareja desde la app».
4. Si no hay hora: «Conecta el USB para fijar la hora» (o Wi-Fi/SNTP).
5. El usuario escanea, conecta USB y la app manda hora + código; el dispositivo
   verifica y pide A.
6. Guarda el emparejamiento y conecta al gateway.
7. Si no hay Wi-Fi, la app puede mandar credenciales por USB o el dispositivo
   abre el SoftAP.

En el simulador actual esto se emula con `gateway/var/virtual_device.json`; en
el hardware será NVS.
