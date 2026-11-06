# Modo reposo y resumen al volver

El dispositivo detecta que no lo estás usando, entra en reposo, sigue vigilando
a los agentes y, cuando vuelves, te enseña qué ha pasado.

> Aprobar y denegar sigue siendo solo del dispositivo. El modo reposo no cambia
> esa regla: si llega un permiso, el dispositivo te avisa.

---

## 1. Objetivo

Que el baton no sea una pantalla que se queda encendida sin más. Cuando no lo
usas:

- Baja la intensidad y muestra una pantalla tranquila con la hora.
- Sigue escuchando a los agentes en segundo plano.
- Al volver, te cuenta lo importante en 5 segundos.

Es el equivalente a que alguien te diga: «mientras estabas fuera, terminaron
dos tareas y una necesita permiso».

---

## 2. Experiencia completa

### 2.1. Uso normal

```
┌──────────────────────────────────────────────┐
│  Dashboard · 3 agentes                       │
│  ┌────────────┐  ┌────────────┐              │
│  │ Auth       │  │ API parser │              │
│  │ trabajando │  │ esperando  │              │
│  └────────────┘  └────────────┘              │
└──────────────────────────────────────────────┘
```

### 2.2. Pasan 5 minutos sin tocar nada

La pantalla se atenúa y entra en reposo:

```
┌──────────────────────────────────────────────┐
│                                              │
│                 14:32                        │
│          viernes, 6 de noviembre             │
│                                              │
│         3 agentes · 2 trabajando             │
│                                              │
│              modo reposo                     │
│       toca o gira el encoder para volver     │
└──────────────────────────────────────────────┘
```

- La hora es grande.
- Debajo, la fecha.
- Un resumen mínimo del estado: cuántos agentes hay y cuántos trabajan.
- Si el gateway se cae, cambia a «sin conexión».
- Sin botones visibles para no invitar a pulsar.
- La pantalla baja el brillo (en el simulador, opacidad).

### 2.3. Vuelves y tocas cualquier control

Aparece el resumen:

```
┌──────────────────────────────────────────────┐
│  Mientras no estabas             12 min      │
│                                              │
│    3            1            1               │
│  terminaron   esperan      falló             │
│                                              │
│  ✓ Auth refactor terminó                     │
│  ! Codex espera permiso                      │
│  ✗ PR fix falló                              │
│                                              │
│  +0,42 $ · +18.400 tokens                    │
│                                              │
│  Pulsa A o toca para volver                  │
└──────────────────────────────────────────────┘
```

- Si no pasó nada: «Todo tranquilo. Nada necesita tu atención».
- Si hay un permiso pendiente, el resumen lo destaca en ámbar y **A** lleva
  directamente a la pantalla de aprobación.
- El resumen se cierra con cualquier control o solo después de 12 segundos.
- Después vuelve el dashboard.

---

## 3. Cuándo entra en reposo

### 3.1. Qué cuenta como actividad

- Girar el encoder.
- Pulsar A, B o PTT.
- Tocar la pantalla (si es táctil en el futuro).
- Mover el ratón o pulsar una tecla en el simulador.

No cuenta como actividad:

- Que un agente cambie de estado.
- Que llegue un mensaje del gateway.
- Que se actualice la hora.
- Que suene un aviso.

### 3.2. Tiempo

- Por defecto: **5 minutos**.
- Configurable entre 1 y 30 minutos.
- Para la demo: `?rest=10` entra en reposo a los 10 segundos.
- `?rest=0` desactiva el modo reposo.

### 3.3. Cuándo NO entra

- Si la pantalla de emparejamiento está abierta.
- Si hay una aprobación pendiente.
- Si el usuario está grabando con PTT.
- Si el detalle de un agente está abierto.
- Si la auditoría está abierta.
- Si el gateway está desconectado (mejor mostrar el estado de conexión).

---

## 4. Qué datos toma mientras está en reposo

Al entrar en reposo guarda una **foto**:

```json
{
  "started_at": "2026-11-06T14:32:00Z",
  "agents": [
    { "id": "opencode:ses_1", "name": "Auth refactor", "status": "running",
      "cost_session": 0.18, "tokens_session": 7200 }
  ],
  "total_cost": 0.28,
  "total_tokens": 11300
}
```

Mientras está en reposo:

- Sigue recibiendo el estado por WebSocket.
- Guarda los cambios importantes en una lista en memoria.
- No pinta el dashboard.
- No acepta ni deniega nada automáticamente.

Al volver compara la foto con el estado actual:

| Antes | Ahora | Resultado |
|---|---|---|
| `running` | `done` o `idle` | terminó |
| `running` | `error` | falló |
| cualquiera | `waiting_input` | espera permiso |
| existía | ya no existe u `offline` | se desconectó |
| no existía | existe | nuevo |

También calcula:

```
tiempo fuera = ahora - started_at
coste extra = total_actual - total_foto
tokens extra = total_actual - tokens_foto
```

Si el coste baja porque el gateway se reinició, se muestra el total actual sin
el signo `+`.

---

## 5. Aprobaciones durante el reposo

Un permiso es urgente: el agente está bloqueado esperando. Pero el dispositivo
**no sale del reposo solo**: se queda mostrando un aviso ámbar para no romper la
calma de la pantalla.

Regla decidida:

1. Llega un `approval_request`.
2. El dispositivo sigue en reposo.
3. Suena un aviso suave y aparece un distintivo ámbar:
   «1 permiso pendiente».
4. El usuario toca o gira el encoder.
5. Se muestra el resumen con el permiso destacado y «A para revisar».
6. Al cerrar el resumen, la pantalla de aprobación queda delante.

Si el usuario no está, el permiso caduca y queda registrado en el resumen.

Ventaja: el reposo no se interrumpe con cada permiso. Riesgo: si el usuario no
mira la pantalla, el aviso puede pasar desapercibido; por eso el distintivo es
grande, ámbar y con un tono suave.

---

## 6. Pantalla de reposo

### 6.1. Contenido

- Hora grande (`14:32`).
- Fecha (`viernes, 6 de noviembre`).
- Estado mínimo: `3 agentes · 2 trabajando`.
- Etiqueta `modo reposo`.
- Pista: `toca o gira el encoder para volver`.
- Un punto que respira lentamente, para que se vea que está vivo.
- Si no hay conexión: `sin conexión` en ámbar.

### 6.2. Comportamiento

- La hora se actualiza cada segundo.
- Si cambia el número de agentes o de trabajando, se actualiza el texto.
- El primer toque o tecla **solo despierta**; no activa el botón que estaba
  debajo.
- El brillo baja al 30–40 %. En el simulador, una capa oscura.
- Si se queda en reposo mucho tiempo, no acumula bucles ni memoria.

---

## 7. Pantalla de resumen

### 7.1. Contenido

- Título: **Mientras no estabas**.
- Tiempo fuera: `12 min`, `2 h`, `desde ayer`.
- Tres números grandes: terminaron, esperan, fallaron.
- Lista de hasta 3 eventos, con nombre del agente y una frase corta.
- Coste y tokens extra.
- Si hay permiso pendiente: aviso ámbar y `A para revisar`.
- Pie: `Pulsa A o toca para volver`.

### 7.2. Casos

- **Todo tranquilo:** solo un mensaje y una marca verde.
- **Solo errores:** borde rojo y el error primero.
- **Permiso pendiente:** borde ámbar y el permiso primero.
- **Muchos eventos:** los 3 más importantes y `+N más`.
- **Sin conexión:** «No se pudo recoger el resumen».

### 7.3. Cierre

- Cualquier control cierra el resumen.
- Si no hay interacción, se cierra solo a los 12 segundos.
- Después vuelve el dashboard.
- Si el usuario sigue sin tocar nada, a los 5 minutos vuelve al reposo.

---

## 8. Dónde guardar el estado de reposo

En el dispositivo real, en RAM: si se reinicia, se pierde y no pasa nada.

En el simulador, en `sessionStorage`:

- `baton.rest` con la foto y la hora de inicio.
- Así una recarga de la pestaña no pierde el resumen.
- Al cerrar el resumen se borra.

No hace falta tocar el gateway para esta feature.

---

## 9. Configuración y demo

- `rest_after_s`: 300 por defecto (5 minutos).
- `?rest=10`: 10 segundos para probar.
- `?rest=0`: desactivado.
- Botón **modo reposo** en las herramientas, junto a **auditoría**: primer clic
  entra en reposo; segundo muestra el resumen; tercero vuelve al dashboard. El
  botón cambia a **despertar** o **cerrar resumen** según el estado.
- La app lo cambia en **Ajustes → Modo reposo**; el gateway lo guarda en SQLite
  y el panel lo lee cada 30 segundos.
- En el hardware, `rest_after_s` se guardará también en NVS.

---

## 10. Pruebas

### Manuales

1. Abrir el panel con `?rest=5`: a los 5 segundos entra en reposo.
2. La hora avanza y el estado de agentes se actualiza.
3. Tocar cualquier tecla: aparece el resumen.
4. El primer toque no pulsa el botón que había debajo.
5. Con un agente terminado: aparece «terminó».
6. Con un agente con error: aparece «falló».
7. Con un permiso pendiente: el resumen lo destaca.
8. Si llega un permiso durante el reposo: sale del reposo y muestra la
   aprobación.
9. El resumen se cierra solo a los 12 segundos.
10. Al volver al dashboard, el modo normal sigue funcionando.
11. `?rest=0`: nunca entra en reposo.
12. Si el gateway se cae en reposo: muestra «sin conexión».

### Criterios de aceptación

- El reposo no oculta un permiso.
- El primer input solo despierta.
- No se pierde el estado al recargar en el simulador.
- No hay bucles ni fugas de memoria.
- La hora y el estado se actualizan sin parpadeos.
- La feature funciona sin hardware.

---

## 11. Fuera de alcance

- Apagar la pantalla físicamente (se hará con el backlight del ESP32).
- Sensores de presencia.
- Resumen generado por IA.
- Enviar el resumen a la app.
- Cambiar el umbral desde la app (queda para Ajustes).

---

## 12. Orden de implementación

1. Detector de inactividad y configuración por URL.
2. Pantalla de reposo con hora y estado.
3. Foto del estado al entrar y comparación al volver.
4. Pantalla de resumen.
5. Despertar con cualquier control, consumiendo el primer input.
6. Prioridad de aprobaciones sobre reposo y resumen.
7. Persistencia en `sessionStorage`.
8. Botones de demo y pruebas.
