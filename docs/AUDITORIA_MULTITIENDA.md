# Auditoría multitienda — FoodOps

**Fecha:** 2026-10-17
**Alcance:** backend `src/foodops`, frontend `foodops-web`, BD local y migraciones.
**Modo:** solo lectura. No se modificó código ni datos.

---

## 0. Resumen ejecutivo

FoodOps **ya es multitienda en gran medida**: el JWT lleva `punto_id`, casi todas
las tablas transaccionales tienen `punto_id NOT NULL`, y la mayoría de los
endpoints toma la tienda del token en vez del cliente. Lo que falta no es
construir el modelo multitienda, sino **cerrar los huecos**:

1. **5 endpoints con IDOR cross-tienda**: cargan un registro por `id` de la URL y
   lo modifican sin verificar que pertenezca a la tienda del usuario.
2. **No existe "Todas las tiendas"** para GERENTE_GENERAL: el patrón actual
   resuelve siempre a *una* tienda; el agregado solo existe en
   `/api/gerencia/dashboard/multi-tienda`.
3. **`punto_id or 0` en el login**: un usuario sin tienda recibe un token con
   `punto_id = 0`, lo que produce listas vacías silenciosas en vez de un error.
4. **No hay validación de pertenencia del `punto_id` solicitado**: `_resolve_punto_id`
   no comprueba que el punto exista ni que sea de la misma empresa.
5. **Cero tests de autorización.** La suite actual (131 líneas) solo cubre
   `/health`, el seed y los modelos.
6. **Frontend sin selector global de tienda**: solo `StockView.vue` tiene uno,
   local a esa vista.

Riesgo real hoy: con 3 tiendas activas, un `resp_tienda` de Centro puede
**liquidar fondos, completar pedidos y recibir reabastecimientos de Jordán o
Auxiliar**, y cualquier usuario autenticado (incluido un cocinero) puede
**cancelar órdenes de otra tienda**.

---

## 1. Nomenclatura: lo pedido vs. lo que existe

Dos diferencias que conviene fijar antes de tocar código.

### 1.1 La columna se llama `punto_id`, no `punto_venta_id`

| Tabla | Columna |
|---|---|
| `ordenes`, `transacciones_venta`, `cajas_diarias`, `gastos`, `desperdicios`, `inventarios_diarios`, `pedidos_reabastecimiento`, `transacciones_pedidos`, `items_inventario`, `usuarios`, `audit_log` | `punto_id` |
| `reglas_reabastecimiento` | `punto_venta_id` *(única excepción)* |

**Decisión propuesta:** mantener `punto_id` como nombre canónico. Renombrar 11
tablas para igualar el enunciado sería una migración destructiva sin beneficio
funcional. En la API pública el query param ya se llama `punto_id`.

### 1.2 Los roles reales no son VENDEDOR/GERENTE

`UserRol` (`src/foodops/db/models.py:12`) define 9 roles:

```
ADMIN, GERENTE_GENERAL, GERENTE_CENTRAL, GERENTE_PUNTO,
RESP_TIENDA, REPARTIDOR, TOMADOR_ORDEN, COCINERO, BODEGUERO
```

Mapeo propuesto a la terminología del pedido:

| Pedido | Rol real | Alcance |
|---|---|---|
| VENDEDOR | `TOMADOR_ORDEN` (y `COCINERO`, `REPARTIDOR`, `BODEGUERO`) | Solo su tienda |
| GERENTE (de tienda) | `RESP_TIENDA`, `GERENTE_PUNTO` | Solo su tienda |
| GERENTE_CENTRAL | `GERENTE_CENTRAL` | Todas, pero solo abastecimiento |
| GERENTE_GENERAL | `GERENTE_GENERAL`, `ADMIN` | Todas |

**No se cambiarán roles de usuarios existentes** (restricción del encargo).

> ⚠️ Gotcha conocido: en PostgreSQL el enum guarda el **nombre** (`'ADMIN'`), pero
> el JWT y las comparaciones de `requiere_rol()` usan el **valor** (`'admin'`).
> Ya está contemplado en el código (`usuario.rol.value` en el login).

---

## 2. Modelos: ¿quién tiene tienda?

### 2.1 Ya tienen `punto_id NOT NULL` ✅

| Modelo | Archivo | Nota |
|---|---|---|
| `Orden` | `models.py:88` | FK a `puntos_venta` |
| `TransaccionVenta` | `models.py:130` | FK |
| `CajaDiaria` | `models_caja.py:26` | FK + `UNIQUE(punto_id, fecha)` |
| `Gasto` | `models_caja.py:48` | **sin FK** (Integer suelto) |
| `Desperdicio` | `models_caja.py:63` | FK |
| `InventarioDiario` | `models_caja.py:103` | FK + `UNIQUE(punto_id, fecha, momento)` |
| `TransaccionPedido` | `models_caja.py:142` | FK |
| `PedidoReabastecimiento` | `models_stock.py:72` | FK |

### 2.2 Tienen tienda opcional (por diseño) ⚠️

| Modelo | Columna | Semántica actual |
|---|---|---|
| `Usuario` | `punto_id` *nullable* | **Ya existe.** NULL = sin tienda asignada |
| `ReglaReabastecimiento` | `punto_venta_id` *nullable* | NULL = regla global de respaldo (intencional, documentado) |
| `ItemInventario` | `punto_id` *nullable* | **Inconsistente — ver §6, decisión pendiente** |
| `AuditLog` | `punto_id` *nullable* | Correcto: hay acciones sin tienda (login fallido) |

### 2.3 Sin tienda (catálogos globales de la empresa) ✅

`Empresa`, `PuntoVenta`, `ProductoMenu`, `ProductoComponente`, `OrdenItem`
(hereda de `Orden`), `TransaccionComponente` (hereda de `TransaccionVenta`),
`InventarioDetalle` (hereda), `PedidoReabastecimientoItem` (hereda),
`FondoRepartidor` (hereda vía `caja_id` → `CajaDiaria.punto_id`).

### 2.4 Cocina

**No existe un modelo de cocina separado.** `KitchenView.vue` consume
`GET /api/ordenes/` y `PUT /api/ordenes/{id}/status`, que ya son tablas con
`punto_id`. No hace falta tabla nueva; sí hace falta arreglar el `PUT` (§4, R1).

---

## 3. Autenticación

**`src/foodops/core/auth.py`**

- `TokenData` ya incluye `punto_id: int` y `rol: str`. ✅
- El JWT **ya lleva la tienda** (`router_auth.py:102`). ✅
- `get_current_user` decodifica el token sin tocar la BD. ✅ (rápido, pero ver R7)
- `requiere_rol(*roles)` es la única dependencia de autorización. **No existe
  ninguna dependencia que valide tienda.** ❌

**Duplicación:** `core/dependencies.py` reimplementa `get_current_user` y añade
`get_current_admin_user`. Ningún router lo importa — es código muerto.

**Problema concreto (`router_auth.py:102`):**

```python
"punto_id": usuario.punto_id or 0,
```

Un `TOMADOR_ORDEN` sin tienda recibe `punto_id = 0`. Todas sus consultas filtran
por `punto_id == 0` → listas vacías, sin error visible. Un `GERENTE_GENERAL` sin
tienda recibe `0` y `/api/gerencia/dashboard` (sin query param) devuelve 404.

**`GET /api/auth/usuarios`** filtra por `current_user.punto_id` ✅, pero un
`GERENTE_GENERAL` solo ve los usuarios de su propia tienda — no puede listar los
de otra (limitación, no vulnerabilidad).

---

## 4. Inventario de endpoints

Leyenda: **TOKEN** = tienda del token · **QUERY** = query param validado ·
**URL** = id de la URL sin validar tienda · **GLOBAL** = sin concepto de tienda.

### 4.1 `router_auth.py`

| Método | Ruta | Roles | Tienda | Estado |
|---|---|---|---|---|
| POST | `/api/auth/login` | público | — | ✅ rate limit por intentos |
| GET | `/api/auth/me` | cualquiera | TOKEN | ✅ |
| GET | `/api/auth/usuarios` | resp_tienda, gerente_general, admin | TOKEN | ⚠️ GG no puede ver otra tienda |

### 4.2 `router_ordenes.py`

| Método | Ruta | Roles | Tienda | Estado |
|---|---|---|---|---|
| POST | `/api/ordenes/` | **cualquiera autenticado** | TOKEN | ⚠️ sin RBAC: un cocinero puede crear órdenes |
| GET | `/api/ordenes/` | cualquiera | QUERY (GG/admin) | ✅ ignora silenciosamente el param si no autorizado |
| PUT | `/api/ordenes/{id}/status` | **cualquiera autenticado** | **URL** | ❌ **R1 — IDOR crítico** |
| GET | `/api/ordenes/reporte/{punto_id}` | admin, GG, gerente_punto | QUERY validado | ✅ |
| POST | `/api/ordenes/transacciones/` | cualquiera | TOKEN | ⚠️ `orden_id` del body no se valida (R6) |
| GET | `/api/ordenes/reporte-rentabilidad/{punto_id}` | admin, GG, gerente_punto | QUERY validado | ✅ |

### 4.3 `router_caja.py` (`_ROLES_TIENDA = resp_tienda, gerente_general, admin`)

| Método | Ruta | Roles | Tienda | Estado |
|---|---|---|---|---|
| POST | `/api/caja/abrir` | TIENDA | TOKEN | ⚠️ GG sin tienda → punto 0 (R3) |
| GET | `/api/caja/actual` | TIENDA | TOKEN | ⚠️ ídem |
| POST | `/api/caja/cerrar` | TIENDA | TOKEN | ⚠️ ídem |
| POST | `/api/gastos` | TIENDA | TOKEN | ✅ |
| GET | `/api/gastos` | TIENDA | TOKEN | ⚠️ GG no puede filtrar otra tienda |
| POST | `/api/desperdicios` | TIENDA | TOKEN | ✅ |
| GET | `/api/desperdicios` | TIENDA | TOKEN | ⚠️ ídem |
| POST | `/api/inventario/items` | GERENCIA | TOKEN | ⚠️ hereda `punto_id` del creador (R8) |
| PUT | `/api/inventario/items/{id}` | GERENCIA | **URL** | ❌ **R5** (bajo: solo gerencia) |
| GET | `/api/inventario/items` | TIENDA + central | **GLOBAL** | ⚠️ catálogo global (R8) |
| GET | `/api/inventario/diario/{momento}` | TIENDA | TOKEN | ✅ |
| POST | `/api/inventario/diario/apertura` | TIENDA | TOKEN | ✅ |
| POST | `/api/inventario/diario/cierre` | TIENDA | TOKEN | ✅ |
| GET | `/api/inventario/consumo` | TIENDA | TOKEN | ⚠️ GG no puede ver otra tienda |
| POST | `/api/fondos-repartidor` | TIENDA | TOKEN (vía caja) | ✅ |
| GET | `/api/fondos-repartidor` | TIENDA | TOKEN (vía caja) | ✅ |
| POST | `/api/fondos-repartidor/{id}/liquidar` | repartidor + TIENDA | **URL** | ❌ **R2 — IDOR** |
| POST | `/api/pedidos` | TIENDA | TOKEN | ✅ |
| PUT | `/api/pedidos/{id}/completar` | TIENDA | **URL** | ❌ **R2 — IDOR** |
| GET | `/api/caja/reporte-cierre` | TIENDA | QUERY (gerencia) | ✅ |

### 4.4 `router_stock.py`

| Método | Ruta | Roles | Tienda | Estado |
|---|---|---|---|---|
| GET | `/api/stock/actual` | TIENDA | QUERY (gerencia) | ✅ |
| GET | `/api/stock/proyeccion` | GERENCIA | QUERY | ✅ |
| GET | `/api/stock/recomendaciones` | GERENCIA | QUERY | ✅ |
| POST | `/api/pedidos-reabastecimiento` | TIENDA | TOKEN | ✅ |
| GET | `/api/pedidos-reabastecimiento` | TIENDA | QUERY (gerencia) | ✅ |
| POST | `/api/pedidos-reabastecimiento/{id}/confirmar` | GERENCIA | **URL** | ⚠️ **R5** (bajo: gerencia ve todo) |
| POST | `/api/pedidos-reabastecimiento/{id}/recibir` | TIENDA | **URL** | ❌ **R2 — IDOR**: altera el stock de otra tienda |
| GET | `/api/productos-menu` | cualquiera | GLOBAL | ✅ catálogo |

### 4.5 `router_abastecimiento.py` (`_ROLES_CENTRAL` ve todas las tiendas por diseño)

| Método | Ruta | Roles | Tienda | Estado |
|---|---|---|---|---|
| GET | `/api/abastecimiento/sugerencias` | CENTRAL | todas (diseño) | ✅ |
| POST | `/api/abastecimiento/pedido/crear` | CENTRAL | body, con validación de existencia | ✅ valida ids inválidos |
| POST | `/api/abastecimiento/pedido/{id}/enviar` | CENTRAL | URL | ✅ aceptable (central es multi-tienda) |
| GET | `/api/abastecimiento/pedidos` | CENTRAL | todas | ✅ |
| GET/POST/PATCH/DELETE | `/api/reglas-reabastecimiento*` | CENTRAL / GERENCIA | todas | ✅ |
| GET | `/api/puntos-venta` | **cualquiera autenticado** | GLOBAL | ⚠️ **R4**: un tomador_orden lista todas las tiendas |
| POST/PATCH/DELETE | `/api/puntos-venta*` | GERENCIA | — | ✅ `DELETE` valida usuarios y órdenes asociadas |

### 4.6 `router_config.py` y `router_gerencia.py`

| Método | Ruta | Roles | Tienda | Estado |
|---|---|---|---|---|
| GET/POST/PATCH | `/api/config/productos*` | GERENCIA | GLOBAL | ✅ catálogo de empresa |
| GET | `/api/gerencia/dashboard` | GERENCIA | QUERY sin validar | ⚠️ `punto_id or current_user.punto_id` → 404 si GG no tiene tienda (R3) |
| GET | `/api/gerencia/dashboard/multi-tienda` | GERENCIA | todas | ✅ único agregado real |

---

## 5. Frontend

**Estado de la tienda (`src/store/index.js`):** Pinia `useAuthStore` con getter
`puntoId` derivado de `/api/auth/me`. **No hay tienda "activa" seleccionable**;
`puntoId` es siempre la del usuario.

**Selector de tienda:** existe **uno solo**, local a `StockView.vue:9`
(`v-if="esGerencia && tiendas.length > 1"`). El resto de las vistas no ofrecen
cambio de tienda.

**Problemas:**

| # | Archivo | Problema |
|---|---|---|
| F1 | `NewOrderView.vue:630` | `punto_id: auth.puntoId \|\| 2` — hardcodea Centro. El backend lo ignora (el schema `CrearTransaccionRequest` no tiene ese campo), pero es un fallback silencioso peligroso si alguna vez se acepta del body. |
| F2 | `router.js:26-48` | Ninguna ruta declara roles en `meta`. El guard solo revisa que exista token. La ocultación por rol vive en `NavBar.vue`, lo que no impide navegar por URL. |
| F3 | — | No hay selector global de tienda para GERENTE_GENERAL ni concepto de "Todas". |
| F4 | `DayClosureView.vue:146` | Si `auth.puntoId` es falsy hace `return` silencioso: pantalla en blanco sin explicación. |

---

## 6. Migraciones y estado de la BD local

**Cadena Alembic (lineal, sin ramas):**

```
001_security_remediation → 002_modulo_d_caja → 003_transacciones_venta
→ 004_stock_reabastecimiento → 005_productos_menu_crud → 006_grupos_elegibles
→ 007_modulo_d_abastecimiento → 008_grupo_elegible_min_max → 009_indices_performance
```

**BD local:** `alembic_version = 009_indices_performance` — al día. ✅

**Puntos de venta (empresa_id = 3):**

| id | nombre |
|---|---|
| 2 | Local Centro |
| 8 | Local Jordán |
| 9 | Local Auxiliar |

**Usuarios (solo 2 en local):**

| id | punto_id | username | rol |
|---|---|---|---|
| 2 | 2 | admin | ADMIN |
| 3 | 2 | central_test | GERENTE_CENTRAL |

**Datos por tienda — todo pertenece a Centro (punto 2):**

| Tabla | Distribución |
|---|---|
| `ordenes` | 40 → punto 2 |
| `transacciones_venta` | 25 → punto 2 |
| `cajas_diarias` | 2 → punto 2 |
| `gastos` | 1 → punto 2 |
| `inventarios_diarios` | 3 → punto 2 |
| `pedidos_reabastecimiento` | 1 → punto 2 |
| `reglas_reabastecimiento` | 40 → punto 2 |
| `desperdicios`, `transacciones_pedidos`, `fondos_repartidor` | vacías |
| **`items_inventario`** | **26 → punto 2, 14 → NULL** ⚠️ |

> ✅ **No hace falta backfill de datos transaccionales.** Toda la data histórica
> es de Centro y ya está etiquetada. El único caso ambiguo es `items_inventario`.

### El problema de `items_inventario` (decisión pendiente)

`items_inventario` se usa de hecho como **catálogo global de la empresa**:

- `GET /api/inventario/items` **no filtra por tienda** — devuelve los 40.
- Las recetas (`producto_componentes`) referencian ids de **ambos grupos**:
  los 14 con `punto_id NULL` (porciones y vegetales) y 8 con `punto_id = 2`
  (Pollo Entero, Arroz, Coditos, Chirmoles, Pepsis…).
- El stock por tienda **no sale de esta tabla**: sale de `inventarios_diarios`
  + `transacciones_venta` + `pedidos_reabastecimiento`, que sí tienen `punto_id`.

Es decir: el `punto_id` de `items_inventario` es **vestigial**. Los 26 valores en
`2` son un accidente de `POST /api/inventario/items`, que copia la tienda del
creador (`router_caja.py:539`).

**Esto importa**: si al "endurecer" el multitienda filtráramos este catálogo por
tienda, Jordán y Auxiliar verían 14 items y **todas las recetas que usan los 8
items de Centro se romperían** en esas tiendas.

---

## 7. Riesgos

| # | Severidad | Riesgo | Ubicación |
|---|---|---|---|
| **R1** | 🔴 **Crítica** | `PUT /api/ordenes/{id}/status` no valida tienda **ni rol**. Cualquier usuario autenticado de Centro puede marcar como entregada o **cancelar** una orden de Jordán conociendo su id (secuencial). | `router_ordenes.py:172` |
| **R2** | 🔴 **Alta** | IDOR cross-tienda en 3 endpoints de escritura operados por `resp_tienda`: liquidar fondo de repartidor ajeno, completar pedido ajeno, **recibir reabastecimiento ajeno** (altera el stock de la otra tienda). | `router_caja.py:913`, `router_caja.py:996`, `router_stock.py:379` |
| **R3** | 🟠 **Media** | `punto_id or 0` en el login. Usuario sin tienda → token con punto 0 → listas vacías silenciosas; GERENTE_GENERAL sin tienda → 404 en su dashboard. No hay constraint que exija tienda a los roles de tienda. | `router_auth.py:102`, `models.py:71` |
| **R4** | 🟠 **Media** | `_resolve_punto_id` no valida que el `punto_id` pedido **exista** ni que sea **de la misma empresa**. Con una segunda empresa en la plataforma, un GERENTE_GENERAL podría leer datos ajenos. Además `GET /api/puntos-venta` está abierto a cualquier rol. | `router_caja.py:67`, `router_stock.py:42`, `router_abastecimiento.py:485` |
| **R5** | 🟡 **Baja** | `PUT /api/inventario/items/{id}` y `POST /pedidos-reabastecimiento/{id}/confirmar` cargan por id sin validar tienda. Mitigado porque ambos exigen rol de gerencia (que legítimamente ve todo), pero rompe el principio de validar siempre. | `router_caja.py:559`, `router_stock.py:344` |
| **R6** | 🟡 **Baja** | `POST /api/ordenes/transacciones/` acepta `orden_id` del body sin verificar que esa orden sea de la tienda del usuario: permite vincular una venta de Centro a una orden de Jordán. | `router_ordenes.py:363` |
| **R7** | 🟡 **Baja** | `get_current_user` no consulta la BD: si a un usuario se le cambia de tienda o se le desactiva, su token sigue válido hasta expirar con la tienda vieja. | `core/auth.py:60` |
| **R8** | 🟡 **Baja** | Inconsistencia de `items_inventario` (§6): tabla usada como catálogo global pero con `punto_id` a medio llenar. | `models_caja.py:78` |
| **R9** | 🟡 **Baja** | `numero_orden = ORD-{YYYYMMDDHHMMSS}` sin tienda ni unicidad: dos tiendas vendiendo en el mismo segundo generan el **mismo número de orden**, que es lo que se imprime en el ticket y se usa en cocina. Con 3 tiendas simultáneas deja de ser teórico. | `router_ordenes.py:71` |
| **R10** | 🟡 **Baja** | Sin tests de autorización. Nada impide que una refactorización futura reintroduzca cualquiera de los anteriores. | `tests/` |
| **R11** | ℹ️ Info | `core/dependencies.py` es código muerto que duplica `core/auth.py`. Invita a importar la versión equivocada. | `core/dependencies.py` |

---

## 8. Plan de implementación

Un commit por paso. Sin `push`, sin deploy, sin tocar producción.

### Paso 1 — `feat: dependencias de alcance multitienda en core/auth`

**Archivo:** `src/foodops/core/auth.py` (+ borrar `core/dependencies.py`)

Añadir el vocabulario que hoy no existe:

```python
ROLES_TODAS_TIENDAS = ("gerente_general", "admin")
ROLES_CENTRAL       = ("gerente_central",)          # multi-tienda, solo lectura/abastecimiento

def usuario_ve_todas_las_tiendas(user: TokenData) -> bool: ...

def resolver_punto_id(user, punto_id, *, permitir_todas=False) -> int | None:
    """Única fuente de verdad del alcance.
    - rol de tienda + punto_id ajeno  -> 403 (hoy se ignora en silencio)
    - rol de tienda sin tienda        -> 400 'usuario sin tienda asignada'
    - GG sin punto_id y permitir_todas-> None  (= todas)
    - GG con punto_id                 -> valida que exista y sea de su empresa
    """

def exigir_acceso_a_punto(session, user, punto_id_del_recurso) -> None:
    """403 si el recurso no es de una tienda que el usuario puede tocar.
    Se llama después de cargar cualquier registro por id de URL."""
```

Reemplazar las tres copias privadas de `_resolve_punto_id` (`router_caja.py:67`,
`router_stock.py:42`, y la lógica inline de `router_ordenes.py`) por esta.

### Paso 2 — `fix: validar tienda en endpoints que cargan por id de URL` (R1, R2, R5, R6)

Insertar `exigir_acceso_a_punto(...)` justo después de cada `session.get(...)`:

| Archivo:línea | Endpoint |
|---|---|
| `router_ordenes.py:172` | `PUT /{orden_id}/status` — **además** añadir `requiere_rol` |
| `router_ordenes.py:363` | validar `orden_id` del body |
| `router_caja.py:559` | `PUT /inventario/items/{id}` |
| `router_caja.py:913` | `POST /fondos-repartidor/{id}/liquidar` (tienda vía `caja_id`) |
| `router_caja.py:996` | `PUT /pedidos/{id}/completar` |
| `router_stock.py:344` | `POST /pedidos-reabastecimiento/{id}/confirmar` |
| `router_stock.py:379` | `POST /pedidos-reabastecimiento/{id}/recibir` |

### Paso 3 — `fix: token sin tienda y 403 explícito en vez de filtro silencioso` (R3)

- `router_auth.py:102`: eliminar `or 0`; emitir `punto_id: null` cuando no hay
  tienda, y `TokenData.punto_id` pasa a `Optional[int]`.
- Un rol de tienda sin `punto_id` → **403 en el login** con mensaje claro
  ("usuario sin tienda asignada, contacte al administrador") en vez de dejarlo
  entrar a una sesión rota.
- `/api/auth/me` devuelve además `punto_nombre` y `ve_todas_las_tiendas`, que el
  frontend necesita para decidir si pinta el selector.

### Paso 4 — `feat: soporte "todas las tiendas" para GERENTE_GENERAL`

Endpoints que pasan a aceptar `punto_id` opcional con semántica *todas* cuando
se omite: `GET /api/gastos`, `GET /api/desperdicios`, `GET /api/inventario/consumo`,
`GET /api/auth/usuarios`, `GET /api/gerencia/dashboard`.
Los agregados añaden `punto_id`/`punto_nombre` por fila para que el frontend
pueda agrupar.

### Paso 5 — `feat: migración 010 — integridad multitienda`

Migración **nueva** (`010_multitienda`), nunca editar las existentes:

- FK faltante `gastos.punto_id → puntos_venta.id`.
- Índice `ix_usuarios_punto_id`.
- `CHECK` en `usuarios`: `punto_id IS NOT NULL OR rol IN ('GERENTE_GENERAL','ADMIN','GERENTE_CENTRAL')`.
- `UNIQUE(punto_id, numero_orden)` + cambiar el formato a `ORD-{punto}-{YYYYMMDDHHMMSS}` (R9).
- `items_inventario`: **pendiente de decisión (§9).**
- `usuarios.punto_id` **ya existe nullable** → no requiere cambio de esquema.

### Paso 6 — `test: suite de aislamiento entre tiendas` (R10)

Infraestructura nueva (hoy no hay tests de API): fixtures con BD SQLite/Postgres
de prueba, usuarios semilla por tienda y helper de token.

Casos exigidos por el encargo:
1. `resp_tienda` de Centro ⇒ `GET /api/ordenes/?punto_id=8` → devuelve Centro, no Jordán.
2. `tomador_orden` de Centro ⇒ `PUT /api/ordenes/{id_de_jordan}/status` → **403**.
3. `resp_tienda` de Centro ⇒ `POST /pedidos-reabastecimiento/{id_de_jordan}/recibir` → **403**.
4. `resp_tienda` de Centro ⇒ `POST /fondos-repartidor/{id_de_jordan}/liquidar` → **403**.
5. `GERENTE_GENERAL` sin `punto_id` ⇒ ve las 3 tiendas; con `?punto_id=8` ⇒ solo Jordán.
6. Usuario de rol de tienda sin tienda ⇒ login **403**.
7. Orden creada siempre lleva el `punto_id` del token, aunque el body mande otro.

### Paso 7 — `feat(web): selector de tienda y alcance en el frontend`

- `store/index.js`: añadir `puntoActivo` (persistido) + `vealTodas`; getter
  `puntoIdEfectivo` que devuelve `null` para "Todas".
- Componente `SelectorTienda.vue` en `NavBar`, visible solo si
  `ve_todas_las_tiendas`.
- Interceptor en `services/api.js`: inyecta `punto_id` en los GET cuando hay una
  tienda específica seleccionada.
- `router.js`: añadir `meta.roles` y hacerlos cumplir en el guard (F2).
- Quitar el fallback `|| 2` de `NewOrderView.vue:630` (F1) y el `return`
  silencioso de `DayClosureView.vue:146` (F4).

### Paso 8 — `refactor: eliminar core/dependencies.py` (R11)

### Paso 9 — Verificación

`pytest` + `uvicorn` en **8001** y `curl` reproduciendo los 7 casos del Paso 6.
Solo contra local — nunca contra `178.156.241.20` ni `asados-foodops.artechgt.com`.

---

## 9. Decisiones pendientes (requieren tu respuesta)

### D1 — `items_inventario`: ¿catálogo global o por tienda? 🔴 bloqueante

Hoy está a medias: 26 items con `punto_id = 2`, 14 con NULL, y el endpoint de
listado ignora la columna. Opciones:

- **(a) Catálogo global de empresa (recomendada).** Poner `punto_id = NULL` en
  los 26 items y dejar de escribir esa columna en `POST /inventario/items`. El
  stock sigue siendo por tienda (sale de `inventarios_diarios`). Es lo que el
  código ya asume y lo único que no rompe las recetas en Jordán/Auxiliar.
- **(b) Catálogo por tienda.** Duplicar los 40 items para los puntos 8 y 9 y
  filtrar el listado por tienda. Implica remapear `producto_componentes`
  (recetas) por tienda — cambio grande y no pedido.
- **(c) No tocar.** Dejar la inconsistencia documentada y nunca filtrar.

### D2 — Usuarios de prueba por tienda

La BD local solo tiene `admin` y `central_test`, ambos en Centro. Para probar el
aislamiento necesito crear usuarios de prueba (ej. `vendedor_centro`,
`resp_jordan`, `gg_test`). ¿Los creo **en la BD local** o solo dentro de las
fixtures de test (sin tocar tu BD)? Por defecto haría **solo fixtures**.

### D3 — Login de un rol de tienda sin tienda asignada

El Paso 3 propone **403 en el login**. La alternativa es dejarlo entrar y que
cada endpoint falle con 400. Prefiero el 403: hoy el `or 0` produce una sesión
silenciosamente rota, que es peor que un error claro.

### D4 — `GET /api/puntos-venta` abierto a todos los roles

El selector de tienda lo necesita, pero solo para GERENTE_GENERAL. Propongo
restringirlo a los roles multi-tienda. Un `tomador_orden` no necesita la lista de
sucursales. ¿Confirmas?

### D5 — Fuera de alcance salvo que indiques lo contrario

- Renombrar `punto_id` → `punto_venta_id` (§1.1): **no**.
- Introducir roles `VENDEDOR`/`GERENTE` (§1.2): **no**, se mapean a los existentes.
- Validación de tienda en `get_current_user` contra BD (R7): **no** en esta
  tanda — añade una consulta por request; lo dejo anotado.

---

## 10. Resultado de la implementación (2026-10-17)

Las decisiones de §9 se resolvieron así: **D1 = (a) catálogo global**,
**D2 = solo fixtures de test** (la BD de desarrollo no recibió usuarios
nuevos), **D4 = restringir** `/api/puntos-venta` a roles multitienda.
D3 y D5 se aplicaron como estaban propuestos.

### Commits

| Commit | Paso |
|---|---|
| `d475089` | `docs:` esta auditoría |
| `ca2f4e6` | `feat:` dependencias de alcance en `core/auth` |
| `5ea3db0` | `fix:` validar tienda en endpoints con id de URL (R1, R2, R5, R6) |
| `b595337` | `fix:` tienda obligatoria en el token (R3) |
| `f8b51a6` | `feat:` alcance "todas las tiendas" + R4 |
| `a0ff150` | `feat:` migración `010_integridad_multitienda` (R8, R9) |
| `08a6c4d` | `test:` suite de aislamiento (R10) |
| `2ba4ac1` | `feat(web):` selector de tienda y roles en rutas |
| `97eb392` | `refactor:` eliminar `core/dependencies.py` (R11) |

Riesgo **R7** (token que sobrevive a un cambio de tienda) queda abierto por
decisión explícita: validarlo costaría una consulta a la BD por request.

### Verificación

`pytest`: **19 pasan** (7 previos + 12 nuevos de aislamiento). Se comprobó
que los tests nuevos **fallan** al revertir la validación, no solo que pasan.

Contra el backend local en 8001:

| Caso | HTTP |
|---|---|
| vendedor de Centro lista sus órdenes | 200 (solo Centro) |
| vendedor de Centro pide `?punto_id=8` | **403** |
| admin pide `?punto_id=8` | 200 |
| admin pide `?punto_id=99999` | **404** |
| responsable de Jordán cancela una orden de Centro | **403** (la orden no cambió de estado) |
| vendedor de Centro lista `/api/puntos-venta` | **403** |
| admin lista `/api/puntos-venta` | 200 |
| `/api/inventario/consumo` sin `punto_id` (admin) | 200, bloque por cada una de las 3 tiendas |
| `/api/inventario/items` | 40 items, todos con `punto_id: null` |

---

## 11. Pasos manuales pendientes (los haces tú)

### ⚠️ Antes de migrar producción: dos consultas de control

La migración 010 **falla y hace rollback** si alguno de estos devuelve filas.
No rompe nada, pero conviene saberlo antes de la ventana de mantenimiento.

```sql
-- 1. Usuarios con rol de tienda y sin tienda: el CHECK los rechaza.
SELECT id, username, rol FROM usuarios
WHERE punto_id IS NULL
  AND rol::text NOT IN ('ADMIN', 'GERENTE_GENERAL', 'GERENTE_CENTRAL');

-- 2. Números de orden repetidos dentro de una misma tienda.
SELECT punto_id, numero_orden, count(*) FROM ordenes
GROUP BY 1, 2 HAVING count(*) > 1;
```

En la BD local ambos devolvieron 0 filas.

### Secuencia de despliegue

1. **Asignar tienda a cada usuario existente** (`UPDATE usuarios SET punto_id = …`).
   Es el paso que desbloquea la consulta 1. Un usuario con rol de tienda y sin
   tienda **ya no podrá iniciar sesión** después de este cambio: recibe un 403
   con el motivo, en vez de la sesión vacía de antes.
2. Aplicar la migración: `alembic upgrade head` (009 → 010).
3. Desplegar backend y frontend. Recordar purgar `sw.js` en Cloudflare tras
   subir el frontend, por el service worker cacheado.
4. **Todos los usuarios deben volver a iniciar sesión.** Los tokens vigentes
   no llevan `empresa_id` y, aunque siguen siendo válidos, se saltan la
   validación de empresa hasta que expiren.

### Cambios de comportamiento que conviene avisar

- Para **gerencia**, omitir `punto_id` en `/api/gastos`, `/api/desperdicios`,
  `/api/inventario/consumo` y `/api/auth/usuarios` ahora significa **todas las
  tiendas**, no "mi tienda". El selector de la NavBar es lo que acota.
- Un rol de tienda que pida `?punto_id=` de otra tienda recibe **403** donde
  antes el parámetro se ignoraba en silencio.
- `gerente_central` ya no puede crear órdenes ni cambiar su estado: su ámbito
  es abastecimiento. Si alguien lo estaba usando como POS, hay que darle un
  rol de tienda.
- Los números de orden nuevos son `ORD-{punto}-{timestamp}`. Los anteriores no
  cambian.
