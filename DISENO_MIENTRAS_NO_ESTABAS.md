# Mientras no estabas

Resumen que aparece al volver a la app para contar qué ha pasado con los agentes
durante el tiempo que no estabas mirando.

> No decide nada y no aprueba nada. Solo informa. Las decisiones siguen en el
> dispositivo.

---

## 1. Objetivo

Que al volver al PC no tengas que leer seis tarjetas para saber qué pasó.

En vez de eso, ves una tarjeta como esta:

```
┌──────────────────────────────────────────────────────────────┐
│  MIENTRAS NO ESTABAS                        hace 2 h  [x]   │
│                                                              │
│  3 terminaron · 1 espera permiso · 1 falló                   │
│                                                              │
│  ✓ Auth refactor terminó: migrar el login a passkeys         │
│  ! Codex espera permiso: npm test -- --coverage              │
│  ✗ PR fix falló: conflicto en package-lock.json              │
│                                                              │
│  2 permisos aprobados · 1 denegado · coste +0,42 $           │
│                                                              │
│  [ Marcar como visto ]                                       │
└──────────────────────────────────────────────────────────────┘
```

Si no ha pasado nada interesante, la tarjeta no aparece.

---

## 2. Qué cuenta

Solo cosas que te importan al volver:

| Situación | Cómo se detecta | Texto |
|---|---|---|
| Un agente terminó | Antes `running` o `waiting_input`, ahora `done` o `idle` | «terminó» |
| Un agente falló | Ahora `error` y antes no | «falló» |
| Un agente espera | Ahora `waiting_input` | «espera permiso» |
| Un agente desapareció | Estaba antes y ya no está, o pasó a `offline` | «se desconectó» |
| Un agente nuevo | Está ahora y no estaba antes | «nuevo» |
| Permisos resueltos | Se aprobaron o denegaron desde el dispositivo | «2 aprobados · 1 denegado» |
| Coste | Diferencia entre el total de antes y el de ahora | «coste +0,42 $» |

No cuenta:

- Cada refresco de estado.
- Cada línea de log.
- Cada cambio de tarea.
- Los agentes ocultos de forma especial: se incluyen, pero con una marca
  discreta.

---

## 3. Cómo sabe qué pasó

No hace falta guardar un historial enorme en el gateway. La app guarda una
**foto** del estado de los agentes y la compara con la foto actual.

### 3.1. Qué se guarda

En el almacenamiento local de la app:

```json
{
  "seen_at": "2026-11-06T09:30:00Z",
  "agents": [
    { "id": "opencode:ses_1", "name": "Auth refactor", "status": "running",
      "task": "Migrar el login", "approval_id": null,
      "cost_session": 0.18, "tokens_session": 7200 },
    { "id": "opencode:ses_2", "name": "API parser", "status": "waiting_input",
      "task": "Revisar parser", "approval_id": "apr_123",
      "cost_session": 0.10, "tokens_session": 4100 }
  ],
  "total_cost": 0.28,
  "total_tokens": 11300
}
```

### 3.2. Cuándo se guarda

- Cuando el usuario pulsa **Marcar como visto**.
- Nunca se actualiza sola en cada refresco: si lo hiciera, se perdería la foto
  de “antes”.
- Si el usuario nunca marca, la foto se queda y el resumen puede repetirse en
  la siguiente apertura. Es aceptable.

### 3.3. Cómo se compara

Se recorren los agentes actuales y los de la foto:

- Si el agente estaba `running` y ahora está `done` o `idle` → terminó.
- Si ahora está `error` y antes no → falló.
- Si ahora está `waiting_input` → espera.
- Si estaba antes y ahora no está, o está `offline` → se desconectó.
- Si está ahora y no estaba antes → nuevo.

El coste y los tokens se restan:

```
coste_delta = total_actual - total_antes
tokens_delta = total_actual - tokens_antes
```

Si el resultado es negativo (porque el gateway se reinició), se muestra el
total actual y se omite el “+”.

---

## 4. Cuándo aparece

La tarjeta aparece:

1. **Al abrir la app**, si hay una foto anterior y hay cambios.
2. **Al volver a la ventana** después de más de 10 minutos sin interacción.
3. **Al pulsar “Resumen”** en la cabecera, si se quiere volver a ver el último
   resumen de la sesión.

No aparece:

- En el primer arranque, porque no hay foto anterior.
- Si no hay cambios y nadie espera.
- Cada 10 segundos.
- Si el gateway está caído.

La tarjeta no es un modal: no bloquea la lista. Se puede cerrar con la X o con
**Marcar como visto**.

---

## 5. Diseño de la tarjeta

- Va arriba de la vista **Agentes**, antes de la barra de búsqueda.
- Fondo oscuro, borde izquierdo de color según lo más importante:
  - rojo si hay errores,
  - ámbar si alguien espera,
  - verde si todo terminó bien.
- Título: **Mientras no estabas**.
- Subtítulo con el tiempo: «hace 2 h», «desde ayer», «hace 3 días».
- Línea de titulares: «3 terminaron · 1 espera permiso · 1 falló».
- Lista de hasta 5 filas; si hay más, «+N más».
- Cada fila es clicable y abre el detalle del agente.
- Línea de permisos y coste.
- Botón **Marcar como visto**.
- X para cerrar y marcar como visto.

En móvil o ventana estrecha, la tarjeta se apila en vertical.

---

## 6. Estados vacíos

- **Primera vez:** no se muestra nada. La foto se crea cuando el usuario pulsa
  “Marcar como visto” o al cerrar la app.
- **Sin cambios:** no se muestra.
- **Solo agentes esperando:** se muestra con borde ámbar.
- **Solo errores:** borde rojo.
- **Todo terminado:** borde verde.
- **Gateway caído:** no se muestra; el banner de conexión ya avisa.

---

## 7. Persistencia

Para la primera versión, `localStorage`:

- Clave `baton.digest`.
- Si el usuario borra la caché de la app, se pierde la foto y no hay resumen esa
  vez. No es grave.

Alternativa si `localStorage` no persiste bien en pywebview:

- Guardar el mismo JSON en `desktop/var/digest.json` mediante el puente.
- La app llama a `load_digest()` / `save_digest()`.
- Es más robusto y también sirve para probar desde Python.

---

## 8. Modo demo

Para enseñar la feature sin esperar dos horas:

- Un botón de desarrollo **Simular ausencia** en la cabecera (solo en modo
  preview o con `BATON_DEV_MODE`).
- Escribe una foto falsa con:
  - un agente `running` que ahora está `idle`,
  - uno `waiting_input`,
  - uno `error`,
  - un coste anterior menor.
- Al pulsarlo, aparece la tarjeta al instante.

También se puede preparar en el modo preview: la app arranca con una foto de
hace 2 horas y los agentes mock ya cambiados.

---

## 9. Pruebas

### Manuales

1. Abrir la app por primera vez: no hay tarjeta.
2. Trabajar, pulsar **Marcar como visto**, cerrar y volver: no hay tarjeta si no
   cambió nada.
3. Con un agente `running`, pulsar **Simular ausencia**: aparece “terminó”.
4. Con un agente `error`: borde rojo y “falló”.
5. Con un agente `waiting_input`: borde ámbar y “espera permiso”.
6. Pulsar una fila: se abre el detalle del agente.
7. Pulsar **Marcar como visto**: la tarjeta desaparece y no vuelve al recargar.
8. Cambiar el coste: el delta se calcula bien.
9. Reiniciar el gateway: si el coste baja, se muestra el total actual sin “+”.

### Criterios de aceptación

- No hay que tocar el gateway para que funcione.
- No se muestran tarjetas en cada refresco.
- No se pierde la foto al refrescar.
- No se muestran botones de aprobar ni denegar.
- La tarjeta se entiende sin abrir ninguna otra pestaña.

---

## 10. Fuera de alcance

- Resumen generado por IA.
- Historial de todos los estados en el gateway.
- Notificaciones mientras la app está cerrada.
- Resumen en el panel de hardware (se puede añadir después).
- Sincronizar la foto entre varios PCs.

---

## 11. Orden de implementación

1. Guardar y leer la foto en `localStorage`.
2. Calcular el resumen comparando foto y estado actual.
3. Pintar la tarjeta y las filas clicables.
4. Botones **Marcar como visto** y **X**.
5. Disparador al abrir la app y al volver a la ventana.
6. Botón **Simular ausencia** para la demo.
7. Pruebas manuales y captura para enseñar la feature.

---

## 12. Resumen en una frase

**“Al volver, la app te cuenta en cinco líneas qué hicieron tus agentes, qué
necesitan y cuánto costó, sin decidir nada por ti.”**
