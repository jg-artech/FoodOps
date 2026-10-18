# Diseño: Impresión por agente de tienda + apertura de cajón

**Fecha:** 2026-10-18 (actualizado el mismo día con las decisiones de §11 de
la versión anterior — ver §11 nueva, "Decisiones confirmadas").
**Fase:** 1 — Auditoría y diseño. **No se implementó nada.**
**Alcance:** backend `src/foodops`, frontend `foodops-web`. Solo lectura del código existente; no se tocó producción ni ninguna impresora real.

---

## 0. Resumen ejecutivo

La arquitectura que proponen (agente local por tienda) es la correcta dado el
constraint real: el backend en Hetzner no puede alcanzar IPs privadas de las
tiendas, y ningún navegador puede abrir un socket TCP crudo — ni siquiera
instalado como PWA. No hay alternativa de "imprimir directo desde el
navegador a la impresora de red" que funcione de verdad; el agente es
obligatorio, no una opción entre varias.

Con todas las decisiones ya confirmadas (§11), el diseño queda así:

1. **El permiso de impresión/cajón es independiente de `_ROLES_TIENDA`.**
   `GERENTE_PUNTO` puede imprimir tickets y abrir el **cajón** (el pulso
   físico a la gaveta), pero sigue sin poder abrir la **caja** financiera
   (`CajaDiaria`), registrar gastos ni tocar fondos de repartidor — eso
   sigue siendo exclusivo de `_ROLES_TIENDA`, sin cambios. Son dos permisos
   distintos aunque suenen parecido; el diseño los separa explícitamente
   (§2).
2. `ADMIN` y `GERENTE_GENERAL` son dos roles distintos en el código, no un
   alias — ambos están en la tabla de permisos de impresión/cajón.
3. El ticket de hoy se arma y convierte a HTML **en el navegador**
   (`ticket.js`), con `window.print()`. El agente no puede ejecutar ese JS —
   el payload que recibe tiene que ser datos estructurados (JSON), no HTML.
4. El token del agente vive en una tabla aparte (`tokens_agente`), no en
   `puntos_venta` — permite rotarlo sin tocar la fila de la tienda y deja
   historial de cada token emitido.
5. El pulso de apertura del cajón, `[0x1B, 0x70, 0x00, 0x19, 0xFA]`, **ya se
   probó físicamente y funciona** con la AON PR-350WF de la tienda de
   prueba — el diseño lo da por bueno sin reservas.

---

## 1. Cómo se imprimen los tickets hoy

**Todo vive en el navegador, no hay nada del lado del servidor.**

- `foodops-web/src/utils/ticket.js` — `buildTicketHtml(orden)` arma un
  documento HTML standalone (CSS `@page { size: 70mm auto }`, fuente
  monoespaciada) a partir del objeto `orden` tal como lo devuelve
  `GET`/`POST /api/ordenes/`. `imprimirTicket(orden)` abre una ventana nueva
  (`window.open`), escribe ese HTML, y el `<body onload="window.print()">`
  dispara el diálogo de impresión nativo del navegador — el usuario elige la
  impresora (configurada como impresora del sistema operativo de la PC/caja)
  y confirma.
- Tres puntos de entrada, los tres llaman a la misma función:
  - `NewOrderView.vue:661` — botón manual "Imprimir" después de confirmar el
    cobro (`step.value = 5`). **No es automático**: el vendedor hace clic.
  - `OrdenList.vue:24` — botón de reimprimir en el listado de órdenes.
  - `OrderCard.vue:44` — mismo botón, en otra vista que lista órdenes.
- `DayClosureView.vue:171` tiene un `imprimir()` separado que es solo
  `window.print()` de la página completa (el reporte de cierre del día, sin
  CSS de impresión dedicado) — es una ruta de impresión distinta, de
  reportes de gerencia, no de tickets de venta. **Confirmado fuera de
  alcance de este diseño** (decisión 5, §11).
- **No existe hoy ningún concepto de "apertura de cajón"** en el código —
  cero referencias a ESC/POS, pulsos, ni gavetas.

**Por qué esto no se puede extender para hablar con la impresora
directamente:** `window.print()` entrega el trabajo al driver de impresión
del sistema operativo de la PC donde corre el navegador — nunca hay un
socket TCP, ni acceso a comandos ESC/POS crudos, ni control sobre el pulso
del cajón. Es una limitación del navegador, no del código actual.

---

## 2. Roles: enum real y permisos (separados de `_ROLES_TIENDA`)

`UserRol` en `src/foodops/db/models.py:12`:

```python
class UserRol(str, enum.Enum):
    ADMIN = "admin"
    GERENTE_GENERAL = "gerente_general"
    GERENTE_CENTRAL = "gerente_central"
    GERENTE_PUNTO = "gerente_punto"
    RESP_TIENDA = "resp_tienda"
    REPARTIDOR = "repartidor"
    TOMADOR_ORDEN = "tomador_orden"
    COCINERO = "cocinero"
    BODEGUERO = "bodeguero"
```

### Dos permisos distintos — no confundir "caja" con "cajón"

El español hace fácil mezclarlos, así que el diseño usa los dos términos sin
ambigüedad a partir de aquí:

- **"Abrir caja" (financiera)** = `POST /api/caja/abrir`, lo que ya existe:
  crea un registro `CajaDiaria` para el día, exige contar el fondo inicial,
  etc. Sigue protegido por `_ROLES_TIENDA = ("resp_tienda",
  "gerente_general", "admin")` en `router_caja.py:53`. **Esto no cambia.**
  `GERENTE_PUNTO` sigue sin poder hacerlo (decisión 1, §11).
- **"Abrir cajón" (física)** = el pulso ESC/POS `[0x1B, 0x70, 0x00, 0x19,
  0xFA]` que hace que la gaveta se abra — es lo nuevo de este diseño, vive
  en su propio permiso, independiente de `_ROLES_TIENDA`.

Dos constantes nuevas (en `router_impresion.py`, no modifican nada de
`router_caja.py`):

```python
# Puede generar un trabajo TICKET.
ROLES_IMPRESION_TICKET = (
    "tomador_orden", "resp_tienda", "gerente_punto",
    "gerente_general", "admin",
)

# Puede generar un trabajo ABRIR_CAJON (automático al confirmar la
# recepción del efectivo vía POST /ordenes/{id}/confirmar-cobro, una sola
# vez por orden - NUNCA al imprimir ni reimprimir -, o manual por el
# botón con motivo). TOMADOR_ORDEN explícitamente fuera.
ROLES_ABRIR_CAJON = (
    "resp_tienda", "gerente_punto", "gerente_general", "admin",
)
```

### Tabla de permisos (confirmada, decisiones 1 y 2 de §11)

| Rol | Imprimir ticket | Abre **cajón** automático (confirmar-cobro, una vez por orden) | Botón "Abrir cajón" (motivo obligatorio) | Abre **caja** financiera / gastos / fondos |
|---|---|---|---|---|
| `TOMADOR_ORDEN` | Sí | **No, nunca** | **No — 403 + audit_log** | No (sin cambios) |
| `RESP_TIENDA` | Sí | Sí | Sí | Sí (sin cambios) |
| `GERENTE_PUNTO` | Sí | Sí | Sí | **No** (sin cambios — `_ROLES_TIENDA` no se toca) |
| `GERENTE_GENERAL` | Sí | Sí | Sí | Sí (sin cambios) |
| `ADMIN` | Sí | Sí | Sí | Sí (sin cambios) |
| `GERENTE_CENTRAL` | No | No | No | No (sin cambios) |
| `REPARTIDOR`, `COCINERO`, `BODEGUERO` | No | No | No | No (sin cambios) |

### `GERENTE_PUNTO`: sin usuarios reales todavía

Verificado en BD local (el patrón de producción coincide, sin tocarla):
**cero usuarios con rol `GERENTE_PUNTO` o `GERENTE_GENERAL` existen hoy**, ni
en local ni en producción. No bloquea el diseño, solo significa que esta
parte de la tabla de permisos no se puede probar end-to-end con una cuenta
real hasta que creen una — lo anoto para la fase de pruebas.

---

## 3. Campos a agregar en `PuntoVenta`

Modelo actual (`src/foodops/db/models.py`), 7 columnas: `id`, `empresa_id`,
`nombre`, `direccion`, `telefono`, `activo`, `created_at`. Sin nada de
impresión.

Los 4 campos que pidieron — **el token del agente NO va aquí** (decisión 3,
§11: tabla aparte, ver §6):

| Campo | Tipo | Nullable | Nota |
|---|---|---|---|
| `impresora_ip` | `String(45)` | sí | IPv4/IPv6 de la impresora en la red local de la tienda. `NULL` = sin impresora configurada todavía. |
| `impresora_puerto` | `Integer` | no, default `9100` | Puerto ESC/POS estándar. |
| `impresora_activa` | `Boolean` | no, default `False` | Flag manual para "esta tienda ya tiene impresora funcionando" — permite activar el flujo por tienda de forma gradual sin que las demás se queden esperando trabajos que nadie va a recoger. |
| `cajon_activo` | `Boolean` | no, default `False` | Independiente de `impresora_activa`: una tienda puede tener impresora pero el cajón desconectado del RJ11, o viceversa. Si es `False`, el backend nunca genera trabajos `ABRIR_CAJON` para esa tienda aunque el rol lo permita. |

Migración futura (no en esta fase): `011_impresion_agente.py`, agregando
estas 4 columnas a `puntos_venta` más las tablas nuevas de §5 y §6, con
defaults explícitos (`impresora_activa`/`cajon_activo` en `False` para
Centro, Jordán y Auxiliar hasta que confirmen cada impresora lista).

---

## 4. Endpoints de caja y audit_log existentes

### `router_caja.py` — relevante para este diseño (sin cambios)

- `_ROLES_TIENDA = ("resp_tienda", "gerente_general", "admin")` (línea 53):
  protege `POST /api/caja/abrir`, `GET /api/caja/actual`,
  `POST /api/caja/cerrar`, `POST/GET /api/gastos`,
  `POST/GET /api/desperdicios`, inventario diario, `fondos-repartidor`. Esta
  constante **no se toca** (decisión 1, §11) — `router_impresion.py` define
  sus propias constantes (§2), no reutiliza ni modifica esta.
- `_ROLES_GERENCIA = ("gerente_general", "admin")` (línea 54): protege CRUD
  de items de inventario.
- Patrón consistente en todo el archivo: `current_user: TokenData =
  Depends(requiere_rol(*_ROLES_TIENDA))`, la tienda sale de
  `exigir_punto_propio(current_user)` (el token), nunca del body —
  `router_impresion.py` sigue el mismo patrón con sus propias constantes.
- `_calcular_efectivo_esperado()` (línea 171) ya suma, de las órdenes con
  `estado_cobro == "cobrada"`, las transacciones en efectivo del día para
  el cuadre de caja (ver §12) — ya desplegado en producción. El trigger
  de apertura automática del cajón (§7) **no se apoya en este cálculo**:
  ocurre dentro de `confirmar_cobro_efectivo()` (`router_ordenes.py`,
  endpoint `POST /api/ordenes/{orden_id}/confirmar-cobro`, ya desplegado),
  en el instante exacto en que `orden.estado_cobro` pasa de
  `"pendiente_recibir"` a `"cobrada"` — nunca al imprimir el ticket.

### `audit_log` (`core/audit.py` + `AuditLog` en `models.py`)

```python
def registrar_auditoria(session, accion, entidad, entidad_id=None,
                         usuario_id=None, punto_id=None, detalle=None, ip=None)
```

Columnas: `id`, `usuario_id`, `punto_id`, `accion`, `entidad`, `entidad_id`,
`detalle` (JSON), `ip`, `created_at`. Ya se usa en absolutamente todas las
acciones sensibles del sistema con el mismo patrón, así que los eventos que
hay que auditar aquí (apertura automática del cajón, apertura manual,
intento denegado de `TOMADOR_ORDEN`, fallo de impresión, regeneración de
token de agente) se registran igual, sin cambios al modelo de auditoría.

---

## 5. Tabla `trabajos_impresion`

`orden_id` incluido (decisión 4, §11). Timeout de reintento confirmado en
30 segundos (decisión 6, §11).

```python
class TipoTrabajoImpresion(str, enum.Enum):
    TICKET = "ticket"
    ABRIR_CAJON = "abrir_cajon"

class EstadoTrabajoImpresion(str, enum.Enum):
    PENDIENTE = "pendiente"
    IMPRIMIENDO = "imprimiendo"
    OK = "ok"
    ERROR = "error"

class TrabajoImpresion(Base):
    __tablename__ = "trabajos_impresion"

    id = Column(BigInteger, primary_key=True)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=False)
    tipo = Column(Enum(TipoTrabajoImpresion), nullable=False)
    # JSON estructurado, NUNCA HTML (ver §9.1) - el agente arma el ESC/POS
    # a partir de esto, no corre JS del navegador.
    payload = Column(JSON, nullable=False, default=dict)
    estado = Column(Enum(EstadoTrabajoImpresion), nullable=False,
                     default=EstadoTrabajoImpresion.PENDIENTE)
    solicitado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    # Obligatorio para ABRIR_CAJON manual; para automático, un valor fijo
    # como "cobro_efectivo"; opcional/NULL para TICKET.
    motivo = Column(String(200), nullable=True)
    orden_id = Column(Integer, ForeignKey("ordenes.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    tomado_at = Column(DateTime, nullable=True)       # el agente lo recogió
    completado_at = Column(DateTime, nullable=True)   # llegó a OK o ERROR
    error = Column(Text, nullable=True)                # detalle si estado=ERROR

    __table_args__ = (
        Index("ix_trabajos_impresion_punto_estado", "punto_id", "estado"),
    )
```

**Timeout de trabajos `IMPRIMIENDO` colgados (confirmado: 30s).** Si el
agente toma un trabajo (`GET pendientes` lo marca `IMPRIMIENDO` +
`tomado_at`) y se cae antes de reportar resultado, un trabajo con
`tomado_at` de hace más de 30 segundos y que sigue `IMPRIMIENDO` vuelve a
aparecer como elegible en el próximo `GET pendientes` (de ese agente o de
otro, si llegaran a correr dos instancias por error).

---

## 6. Tabla `tokens_agente` (tabla aparte, decisión 3 de §11)

Un token por tienda, en su propia tabla — permite **rotar un token sin
tocar la fila de `puntos_venta`** (solo se inserta una fila nueva y se
desactiva la vieja) y deja **historial de cada token emitido** (quién lo
generó, cuándo, cuándo se revocó) para auditoría si alguna vez se sospecha
de un token comprometido.

```python
class TokenAgente(Base):
    __tablename__ = "tokens_agente"

    id = Column(Integer, primary_key=True)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)  # sha256 hex
    activo = Column(Boolean, nullable=False, default=True)
    creado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    revocado_at = Column(DateTime, nullable=True)
    # Heartbeat del agente (decisión 7, §11) - se actualiza solo, como
    # efecto lateral de la autenticación en CADA request del agente. No
    # hace falta que el agente llame a un endpoint aparte para esto: su
    # loop normal de GET pendientes cada pocos segundos ya lo alimenta.
    ultima_conexion_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_tokens_agente_punto_activo", "punto_id", "activo"),
        # A nivel de BD, a lo sumo un token activo por tienda a la vez
        # (índice único parcial de Postgres).
        Index(
            "ux_tokens_agente_punto_unico_activo", "punto_id",
            unique=True, postgresql_where=text("activo = true"),
        ),
    )
```

- **Generación/rotación**: `POST /api/puntos-venta/{id}/regenerar-token-agente`
  (solo `ADMIN`/`GERENTE_GENERAL`). Genera un secreto de alta entropía
  (`secrets.token_urlsafe(32)`), lo devuelve **una sola vez** en la
  respuesta, inserta la fila nueva en `tokens_agente` con `sha256(token)`, y
  en la misma transacción marca `activo=False, revocado_at=now()` en la fila
  anterior de esa tienda (si existía). El texto plano del token no se guarda
  en ningún lado del backend ni del repo.
- **Por qué SHA-256 y no bcrypt**: el agente va a hacer polling cada pocos
  segundos — bcrypt está diseñado para ser lento a propósito (defensa contra
  fuerza bruta de contraseñas humanas de baja entropía), lo que lo vuelve
  contraproducente aquí: cada poll pagaría ~100ms+ de cómputo innecesario.
  Un token aleatorio de 256 bits no es adivinable por fuerza bruta aunque el
  hash sea rápido — el mismo criterio que ya usa el proyecto para JWT
  (HMAC-SHA256, no bcrypt).
- **Dónde vive el token real**: en la configuración local del agente
  (archivo de config o variable de entorno — Python, decisión 8 de §11). El
  admin lo copia una vez al generarlo y lo pega ahí. Si se pierde o se
  compromete, se regenera: la fila vieja queda revocada, cualquier agente
  que siga usando el token anterior empieza a recibir 401 de inmediato.
- **Transporte**: header `Authorization: Bearer <token>` en cada request del
  agente — un espacio de autenticación separado del JWT de usuarios (no pasa
  por `requiere_rol`). Dependencia nueva `requiere_agente()`: busca en
  `tokens_agente` la fila con `token_hash == sha256(token recibido)` y
  `activo = true`, de ahí saca `punto_id` y actualiza `ultima_conexion_at` —
  **el agente nunca manda su propio `punto_id`**, se deriva del token, igual
  que `exigir_punto_propio()` ya hace con los usuarios.

---

## 7. Endpoints propuestos

Nuevo router, `router_impresion.py`, prefix `/api/impresion` (cruza caja y
órdenes, no encaja limpio en ninguno de los dos existentes).

### Para el agente (autenticado con el token de tienda, §6)

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/api/impresion/agente/pendientes` | Devuelve los trabajos `PENDIENTE` (o `IMPRIMIENDO` vencidos hace +30s, §5) de la tienda del token, y los marca `IMPRIMIENDO` + `tomado_at` en la misma transacción. Como efecto lateral de la autenticación, actualiza `ultima_conexion_at` (heartbeat). |
| `POST` | `/api/impresion/agente/trabajos/{id}/resultado` | Body `{estado: "ok"|"error", error?: string}`. Actualiza el trabajo. 404 si el trabajo no pertenece a la tienda del token. También actualiza `ultima_conexion_at`. |

### Para el usuario (JWT normal, como todo lo demás)

| Método | Ruta | Roles | Qué hace |
|---|---|---|---|
| `POST` | `/api/impresion/ticket` | `ROLES_IMPRESION_TICKET` (§2) | Body `{orden_id}`. Arma el `payload` JSON a partir de la orden (reutilizando lo que hoy arma `_orden_dict`), crea el trabajo `TICKET`. **Nunca** crea un trabajo `ABRIR_CAJON` — imprimir o reimprimir (botón manual, cualquier número de veces) no abre el cajón bajo ninguna circunstancia; eso ya pasó (o no) en `confirmar-cobro` (ver fila siguiente y §12). Momento en que el frontend llama a este endpoint, según `metodo_pago`: si es `"efectivo"`, **después** de que `ROLES_ABRIR_CAJON` confirme la recepción (`POST /ordenes/{id}/confirmar-cobro`, §12); si es `"tarjeta"` o `"transferencia"`, **al cobrar** — no hay recepción física que confirmar en esos métodos, así que no hay nada que esperar. |
| `POST` (ya existe, `router_ordenes.py`, fuera de este router) | `/api/ordenes/{orden_id}/confirmar-cobro` | mismo set de roles que `ROLES_ABRIR_CAJON` (§2) — ya implementado así en producción | **Ya desplegado**, no es parte de este diseño. Mueve `orden.estado_cobro` de `"pendiente_recibir"` a `"cobrada"` (§12). **Es el único punto de todo el sistema que crea el trabajo `ABRIR_CAJON` automático** (`motivo="cobro_efectivo"`, `orden_id` de la orden), y lo crea **una sola vez por orden**: si ya existe un trabajo `ABRIR_CAJON` con ese `orden_id`, no crea otro, así se reintente la confirmación o se reimprima el ticket cualquier cantidad de veces después. |
| `POST` | `/api/impresion/abrir-cajon` | `ROLES_ABRIR_CAJON` (§2) | Body `{motivo: str}` obligatorio (mínimo ~5 caracteres). `TOMADOR_ORDEN` → 403 + `registrar_auditoria(accion="INTENTO_ABRIR_CAJON_DENEGADO", ...)`. Cualquier otro rol fuera de `ROLES_ABRIR_CAJON` → 403. **Nota de nombre**: la ruta se llama `abrir-cajon`, no `abrir-caja`, a propósito — `abrir-caja` ya existe en `router_caja.py` y es la apertura financiera del día, algo completamente distinto. Este es el botón **manual**, independiente del automático de `confirmar-cobro`. |
| `GET` | `/api/impresion/trabajos` | cualquiera de `ROLES_IMPRESION_TICKET` | `?punto_id=` (gerencia) `&orden_id=` `&estado=`. Para que el frontend muestre "tu ticket: ✅ impreso / ⏳ pendiente / ❌ falló, reintentar". |
| `POST` | `/api/impresion/trabajos/{id}/reintentar` | igual que quien lo creó o gerencia de esa tienda | Solo si `estado == "error"`. Vuelve a `PENDIENTE`, limpia `error`, no crea un trabajo nuevo (mismo `id`, mismo `created_at`, para no perder trazabilidad). |
| `GET` | `/api/impresion/agente/estado` | `_ROLES_TIENDA` + `GERENTE_PUNTO` (gerencia/responsable de esa tienda) | `?punto_id=`. Heartbeat (decisión 7, §11): `{conectado: bool, ultima_conexion_at}`. "Conectado" = `ultima_conexion_at` dentro de los últimos 30 segundos — mismo margen que el timeout de §5, y coherente con un agente que haga poll cada ~5-10s (valor recomendado para la fase de implementación del agente, no bloqueante aquí). |
| `POST` | `/api/puntos-venta/{id}/regenerar-token-agente` | `ADMIN`/`GERENTE_GENERAL` | Ver §6. Devuelve el token en texto plano **una sola vez**. |

**Reutilización explícita, no reinventar**: `exigir_punto_propio`,
`exigir_acceso_a_punto`, `requiere_rol`, `registrar_auditoria` ya existen en
`core/auth.py` y `core/audit.py` y cubren exactamente lo que estos
endpoints necesitan — el router nuevo los importa, no duplica lógica de
autorización.

---

## 8. Qué pasa si el agente está apagado o la impresora no responde

Regla rectora, tal como la pidieron: **la venta nunca se bloquea por la
impresora.**

1. `POST /api/ordenes/` y `POST /api/ordenes/transacciones/` (el cobro en
   sí) **no cambian** — siguen guardando la venta de forma completamente
   independiente de si hay o no agente conectado.
2. `POST /api/impresion/ticket` responde de inmediato con el trabajo creado
   en `PENDIENTE` — no espera a que nadie lo imprima. El frontend no
   bloquea ningún botón mientras tanto. El trabajo `ABRIR_CAJON`
   automático sigue la misma regla pero nace en otro lado: se crea en
   `PENDIENTE` dentro de `POST /api/ordenes/{orden_id}/confirmar-cobro`
   (§7, §12), no en este endpoint — tampoco espera a que el agente esté
   conectado para quedar encolado.
3. **Agente apagado** (la PC de la tienda está apagada, o el agente no
   corre): el trabajo se queda en `PENDIENTE` indefinidamente. Cuando el
   agente vuelva a conectarse — en 5 minutos o al día siguiente — lo recoge
   en su próximo `GET pendientes` y lo imprime igual, aunque tarde. No hace
   falta ninguna acción del usuario para esto. En el panel, `GET
   /api/impresion/agente/estado` mostraría `conectado: false` apenas pasen
   30s sin que el agente haga poll — el gerente puede ver esto sin
   necesidad de que nadie reporte "la impresora no sirve".
4. **Agente prendido pero la impresora específica falla** (sin papel,
   apagada, cable Wi-Fi caído): el agente intenta el socket TCP, falla, y
   reporta `POST resultado {estado: "error", error: "..."}`. El trabajo
   queda en `ERROR`, visible para el usuario con el botón de reintentar
   (§7). Aquí el agente sí está `conectado: true` (sigue haciendo poll),
   pero el trabajo específico falló — son señales independientes.
5. El frontend puede hacer un polling corto y silencioso tras crear el
   trabajo (p. ej. cada 3s durante 15-20s) solo para mostrar una
   notificación discreta de "✅ impreso" o "❌ no se pudo imprimir, reintentar" —
   nunca para bloquear la UI. Si el agente tarda más que esa ventana (estaba
   apagado), simplemente no se muestra nada más y el trabajo queda
   disponible en el listado de `GET /api/impresion/trabajos` para revisar
   después.

---

## 9. Decisiones de arquitectura adicionales

### 9.1 El payload tiene que ser JSON estructurado, no HTML

Es la consecuencia directa de que el agente es un proceso aparte (no un
navegador): no puede ejecutar `buildTicketHtml()` ni interpretar CSS de
`@page`. El backend arma un JSON con los mismos campos que ya devuelve
`_orden_dict()` (numero_orden, items, total, cliente, método de pago,
punto_nombre...) y **el agente es responsable de convertir eso a los bytes
ESC/POS** (comandos de inicialización, CP850, corte de papel). Esto es
deliberado: si cambian de modelo de impresora en el futuro, el cambio vive
solo en el agente, el backend no sabe nada de ESC/POS.

### 9.2 Dónde vive el código del agente

Este documento diseña el backend y las tablas nuevas. El agente en sí (la
pieza que hace polling y habla ESC/POS por socket con la AON PR-350WF) es un
programa Python aparte (decisión 8, §11) que corre en la PC de cada tienda
— no es parte de `foodops-web` ni de `src/foodops`. El empaquetado para
Windows (ejecutable con `pyinstaller`, servicio, inicio automático...) se
decide en la fase de diseño del agente, no en esta.

### 9.3 Pulso de apertura del cajón: confirmado físicamente

**Decisión 9 de §11**: el comando `[0x1B, 0x70, 0x00, 0x19, 0xFA]` (`ESC p 0
25 250`) ya se probó en la AON Business PR-350WF real y **abrió la gaveta
físicamente**. El diseño de apertura automática/manual de §7 usa este
comando sin reservas ni alternativas — no hace falta investigar variantes
de pin ni parámetros de pulso distintos para este modelo.

---

## 10. Resumen de hallazgos de la auditoría

1. La impresión actual vive 100% en el navegador (`ticket.js` +
   `window.print()`) — no hay nada reutilizable del lado del servidor para
   el agente; hay que construir el payload JSON desde cero en el backend.
2. `GERENTE_PUNTO` no tiene hoy ningún permiso de caja (`_ROLES_TIENDA` no
   lo incluye) y **sigue sin tenerlo tras este diseño** — su permiso de
   impresión/cajón es una vía separada (§2), no una ampliación de
   `_ROLES_TIENDA`.
3. `ADMIN` y `GERENTE_GENERAL` son roles separados en el código, no un
   alias — ambos están en `ROLES_IMPRESION_TICKET` y `ROLES_ABRIR_CAJON`.
4. Ningún otro rol (`REPARTIDOR`, `COCINERO`, `BODEGUERO`, `GERENTE_CENTRAL`)
   tiene ni debería tener acceso a caja ni a cajón.
5. `PuntoVenta` no tiene ninguna columna de impresión hoy; se agregan 4
   (`impresora_ip`, `impresora_puerto`, `impresora_activa`, `cajon_activo`).
   El token del agente vive en su propia tabla (`tokens_agente`), no aquí.
6. El patrón de autorización del proyecto (`requiere_rol`,
   `exigir_punto_propio`, `exigir_acceso_a_punto`, `registrar_auditoria`) ya
   cubre todo lo que estos endpoints nuevos necesitan.
7. Existe una segunda ruta de impresión (`DayClosureView.vue`, reporte de
   cierre del día) completamente distinta a los tickets de venta — confirmado
   fuera de alcance.
8. Cero usuarios reales con rol `GERENTE_PUNTO` o `GERENTE_GENERAL` hoy — la
   parte de la tabla de permisos que los involucra no se puede probar
   end-to-end hasta crear una cuenta de prueba.
9. El pulso de apertura del cajón ya se validó físicamente contra la
   impresora real — el diseño no depende de una suposición sin probar.

---

## 11. Decisiones confirmadas (2026-10-18)

Respuestas a las 9 preguntas de la versión anterior de este documento, ya
incorporadas en todas las secciones de arriba:

1. **`GERENTE_PUNTO` no se agrega a `_ROLES_TIENDA`.** El permiso de
   impresión/cajón se maneja aparte, en `ROLES_IMPRESION_TICKET` /
   `ROLES_ABRIR_CAJON` (§2).
2. **`ADMIN` incluido junto con `GERENTE_GENERAL`** en toda la tabla de
   permisos de apertura de cajón (§2).
3. **Tabla aparte `tokens_agente`** (§6), no columna en `puntos_venta` —
   permite rotar el token sin tocar la fila de la tienda.
4. **`orden_id` incluido** en `trabajos_impresion` (§5).
5. **`DayClosureView.vue` fuera de alcance** en esta fase (§1).
6. **Timeout de 30 segundos** confirmado para trabajos `IMPRIMIENDO`
   colgados (§5).
7. **Heartbeat del agente incluido** en esta fase (§6, §7, §8) — se
   implementa como efecto lateral de la autenticación en cada request del
   agente, sin necesitar un endpoint `/heartbeat` dedicado, más un endpoint
   de lectura `GET /api/impresion/agente/estado` para el panel.
8. **Agente en Python.** El empaquetado para Windows se decide en la fase
   de diseño del agente, no en esta.
9. **Prueba del cajón confirmada exitosa** con el pulso `[0x1B, 0x70, 0x00,
   0x19, 0xFA]` contra la AON PR-350WF real (§9.3).

No quedan preguntas pendientes de esta ronda. El diseño está listo para
pasar a Fase 2 (implementación) cuando lo autoricen — **sigo detenido, no
he implementado nada.**

---

## 12. Recepción de efectivo (ya desplegado — contexto del que depende §7)

Esta sección no es parte de lo que diseña este documento (impresión +
cajón): documenta el flujo de cobro en efectivo que **ya está implementado
y desplegado en producción** (otra iniciativa, ya cerrada), porque §7
engancha la apertura automática del cajón a ese flujo en vez de a la
impresión.

- `Orden.estado_cobro` (`src/foodops/db/models.py`, migración
  `011_estado_cobro.py`) es un campo **independiente** de `Orden.estado`
  (el workflow de cocina: pendiente/preparando/listo/entregado/cancelado).
  Dos valores posibles: `"pendiente_recibir"` | `"cobrada"`.
- Una orden en efectivo nace con `estado_cobro = "pendiente_recibir"`
  (`POST /api/ordenes/`). Tarjeta y transferencia nacen directo en
  `"cobrada"` — no hay nada físico que confirmar en esos métodos.
- `POST /api/ordenes/{orden_id}/confirmar-cobro` (`router_ordenes.py`, ya
  desplegado) es el único endpoint que mueve `estado_cobro` de
  `"pendiente_recibir"` a `"cobrada"`, registrando `monto_recibido`,
  `vuelto_entregado`, `confirmado_por` y `confirmado_at`. Protegido por el
  mismo conjunto de roles que `ROLES_ABRIR_CAJON` (§2): `resp_tienda`,
  `gerente_punto`, `gerente_general`, `admin` — `tomador_orden` no puede
  confirmar su propio cobro.
- Una segunda llamada a `confirmar-cobro` sobre la misma orden (ya
  `"cobrada"`) devuelve `400` con `detail="Esta orden ya fue cobrada"`
  (`router_ordenes.py:342-343`) **antes** de llegar a las asignaciones de
  `monto_recibido`/`vuelto_entregado`/`confirmado_por`/`confirmado_at` —
  no las sobrescribe. Cubierto por
  `test_no_se_puede_confirmar_cobro_dos_veces`
  (`tests/integration/test_cobro_efectivo.py:269-282`).
- `_calcular_efectivo_esperado()` (`router_caja.py`, §4) solo cuenta, para
  el cuadre del día, transacciones en efectivo de órdenes con
  `estado_cobro == "cobrada"` — una orden todavía `pendiente_recibir` no
  suma al cuadre.
- **Por qué le importa a este diseño**: §7 crea el trabajo `ABRIR_CAJON`
  automático dentro de `confirmar_cobro_efectivo()`, en el instante exacto
  en que `estado_cobro` pasa a `"cobrada"` — no en `POST
  /api/impresion/ticket`. Imprimir el ticket y abrir el cajón quedan como
  dos acciones independientes, con disparadores distintos y en momentos
  distintos (ticket de efectivo: después de confirmar-cobro; ticket de
  tarjeta/transferencia: al cobrar, ver §7).

**Pendiente, sin decidir**: si al registrar una orden en efectivo (queda en
`estado_cobro = "pendiente_recibir"`, antes de que nadie confirme nada) se
debe imprimir de una vez una comanda provisional para cocina, o si cocina
debe esperar a que se confirme el cobro igual que el cajón. No hay
decisión tomada todavía — queda abierto para la siguiente ronda, no lo
estoy decidiendo aquí.
