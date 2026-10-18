# Auditoría: flujo de cobro en efectivo

**Fecha:** 2026-10-18
**Fase:** 1 — Auditoría, solo lectura. **No se implementó nada.**
**Alcance:** backend `src/foodops`, frontend `foodops-web`. No se tocó producción ni `.env*`.

---

## 0. Hallazgo crítico — léelo antes del resto

**`Orden.estado` hoy es la variable de estado de la *cocina*, no del cobro,**
y está profundamente enganchada a eso en el frontend. Las "decisiones
confirmadas" de tu mensaje dicen "la orden queda `PENDIENTE_RECIBIR`" y
"pasa a `COBRADA`" — si eso se implementa como valores nuevos de la misma
columna `Orden.estado`, **rompe la pantalla de cocina**, no es una
ampliación inocua. El detalle completo está en §2, pero el resumen es:

- `OrdersListView.vue` tiene tabs literales `pendiente` / `preparando` /
  `listo` / `entregado`, con botones que comparan `orden.estado === 'pendiente'`
  exacto para decidir qué acción mostrar.
- `KitchenView.vue:100` decide qué órdenes mostrarle a cocina con
  `['pendiente', 'preparando'].includes(o.estado)`.
- `POSMainView.vue` cuenta pendientes/preparando/listo para el dashboard del
  POS con el mismo criterio.

Si una orden en efectivo nace en `pendiente_recibir` en vez de `pendiente`,
**cocina nunca la ve** — ese filtro no la va a capturar, y nadie la prepara
hasta que alguien confirme el cobro, lo cual no tiene que ver con si ya se
coció el pollo o no. Preparar la comida y cobrarla son dos cosas que pasan
en paralelo, no en secuencia, y hoy solo hay un campo para las dos.

**No lo resuelvo yo en esta fase** (es Fase 1, solo auditoría) pero lo
marco como la pregunta que bloquea empezar Fase 2 tal como está escrita tu
instrucción — ver la pregunta al final del documento.

---

## 1. Flujo actual de pago en efectivo

Dos llamadas separadas desde `NewOrderView.vue` (`foodops-web/src/views/NewOrderView.vue:629-645`),
la segunda sin esperar a que termine (`.catch(() => {})`, fire-and-forget):

### `POST /api/ordenes/` (`router_ordenes.py:87-150`, función `crear_orden`)

Crea la fila `Orden` con, entre otros:

```python
dinero_recibido=float(orden.dinero_recibido) if orden.dinero_recibido is not None else None,
vuelto=float(orden.vuelto) if orden.vuelto is not None else None,
estado=OrdenEstado.PENDIENTE,   # SIEMPRE, sin importar el método de pago
```

`dinero_recibido` y `vuelto` vienen del body (`OrdenCreate.dinero_recibido`,
`.vuelto`) **tal como los calculó el frontend** — el backend no recalcula ni
valida nada (no verifica `dinero_recibido >= total`, no verifica que
`vuelto == dinero_recibido - total`). Quien los escribe es el mismo
`TOMADOR_ORDEN` que está creando la orden, en el momento de crearla — **no
hay ningún paso donde el responsable confirme lo que realmente recibió**.
Es exactamente el hueco que describes en tu contexto.

`estado` nace siempre en `PENDIENTE`, sin importar si el método de pago es
efectivo, tarjeta o transferencia — hoy no existe ningún concepto de "orden
sin cobrar" vs. "orden cobrada".

### `POST /api/ordenes/transacciones/` (`router_ordenes.py:392-452`, función `crear_transaccion`)

Crea una fila `TransaccionVenta` separada, vinculada por `orden_id`:

```python
estado="completada",   # hardcodeado, nunca cambia, no se parametriza (línea 444)
```

**Esta fila nunca cambia de estado.** No hay ningún código en todo el
backend que escriba `TransaccionVenta.estado` a otro valor — grep completo
de `TransaccionVenta.estado =` no devuelve ninguna asignación fuera de esta.
Lo confirma que haya 3 lugares que *leen* `estado == "completada"`
(`router_ordenes.py:488`, `router_caja.py:851`, `router_caja.py:1144`) pero
cero que lo escriban con otro valor — ese filtro hoy es un no-op, siempre es
verdadero.

### Cuándo entra al cuadre

**Inmediatamente**, en el mismo instante en que se crea la `TransaccionVenta`
— no cuando alguien "cobra" nada. `_calcular_efectivo_esperado()` (§4) suma
*todas* las `TransaccionVenta` con `metodo_pago == "efectivo"` del día, sin
mirar si la `Orden` asociada sigue viva o fue cancelada después. Esto
significa que **hoy, cancelar una orden en efectivo después de que se creó
la transacción no la saca del cuadre** — el dinero "esperado" sigue
contándola. Ver §6 para el detalle completo de esto, que es el bug más
serio que encontré en esta auditoría.

---

## 2. Estados actuales

### `Orden.estado` (`OrdenEstado`, `models.py:23-28`)

```python
class OrdenEstado(str, enum.Enum):
    PENDIENTE = "pendiente"
    PREPARANDO = "preparando"
    LISTO = "listo"
    ENTREGADO = "entregado"
    CANCELADO = "cancelado"
```

Es **la variable de estado de la cocina**. Consumida por exact-string-match
en:

| Archivo | Uso |
|---|---|
| `OrdersListView.vue:32,37,42,47` | Tabs y botones de acción (`pendiente`→`preparando`→`listo`→`entregado`, botón cancelar visible solo si `['pendiente','preparando']`) |
| `KitchenView.vue:100` | `['pendiente', 'preparando'].includes(o.estado)` decide qué le aparece a cocina |
| `POSMainView.vue:73-75` | Contadores del dashboard del POS |
| `OrdenList.vue:19-20`, `OrderCard.vue:84,92,10` | Color/badge según el valor exacto |

No hay ningún campo separado para "¿ya se cobró?" — ni en el modelo, ni en
ningún endpoint, ni en ninguna vista.

### `TransaccionVenta.estado` (`models.py`, columna `String(50)`, no es un enum de Python)

Solo tiene **un valor posible en la práctica hoy**: `"completada"`,
hardcodeado al crear (línea 444 de `router_ordenes.py`), nunca reescrito.
No es un `enum.Enum` en el código — es un `String` libre, así que técnicamente
se podría escribir cualquier string, pero nada en el sistema lo hace hoy.

---

## 3. `dinero_recibido` y `vuelto`: ¿se persisten?

**Sí, se persisten** — son columnas reales en `Orden` (`models.py`,
`Float`, ambas nullable). No es solo un cálculo que se muestra y se
descarta.

Pero lo que se persiste es **el cálculo del vendedor al momento de crear la
orden**, no una confirmación posterior de nadie más:

- `NewOrderView.vue:331-333`: `vuelto = computed(() => Number(form.dinero_recibido) - totalPrecio.value)` —
  cálculo puramente en el navegador, en el mismo formulario donde se arma la
  orden.
- Ese `vuelto` calculado y el `dinero_recibido` que el vendedor tecleó viajan
  tal cual en el body de `POST /api/ordenes/` y el backend los guarda sin
  tocarlos (`crear_orden`, arriba).
- No existe ningún endpoint que permita a otro usuario (el responsable)
  escribir un `dinero_recibido`/`vuelto` *distinto* después — una vez
  creada la orden, esos dos campos quedan fijos para siempre con lo que
  escribió el vendedor.

---

## 4. `_calcular_efectivo_esperado()` — qué suma exactamente

**Archivo:** `src/foodops/api/router_caja.py`, **líneas 171–204**.

```python
def _calcular_efectivo_esperado(session, caja: CajaDiaria) -> Decimal:
    day_start, day_end = _day_bounds(caja.fecha)

    ventas_efectivo = session.execute(
        select(func.coalesce(func.sum(TransaccionVenta.precio_venta), 0)).where(
            TransaccionVenta.punto_id == caja.punto_id,
            TransaccionVenta.metodo_pago == "efectivo",
            TransaccionVenta.created_at >= day_start,
            TransaccionVenta.created_at < day_end,
        )
    ).scalar_one()
    # ... gastos_total, fondos_pendientes, fondos_liquidados_hoy (sin cambios relevantes aquí)
    return (
        Decimal(str(caja.fondo_inicial))
        + Decimal(str(ventas_efectivo))
        - Decimal(str(gastos_total))
        - Decimal(str(fondos_pendientes))
        + Decimal(str(fondos_liquidados_hoy))
    )
```

Suma `TransaccionVenta.precio_venta` filtrando solo por `punto_id`,
`metodo_pago == "efectivo"` y el rango de fecha del día de la caja.
**No filtra por `TransaccionVenta.estado`** (a diferencia de las otras 3
lecturas de ese campo en el resto del código) **y no mira en absoluto el
`Orden.estado` de la orden asociada.** Una venta en efectivo cuya orden fue
cancelada después sigue sumando aquí igual que una que sí se entregó y
cobró.

---

## 5. ¿El cierre de caja valida órdenes sin cobrar?

**No, ninguna validación de este tipo existe hoy.**

`cerrar_caja()` (`router_caja.py:363-412`) solo valida una cosa antes de
cerrar: que el conteo de inventario de cierre (`InventarioDiario`, momento
`"cierre"`) esté `completado`. No hay ninguna consulta a `Orden` en toda la
función — ni para ver si hay órdenes `PENDIENTE`, ni `PREPARANDO`, nada. Se
puede cerrar caja con órdenes activas en cualquier estado.

---

## 6. Cancelación de órdenes por `TOMADOR_ORDEN`

`actualizar_estado_orden()` (`router_ordenes.py:221-253`):

```python
@router.put("/{orden_id}/status")
def actualizar_estado_orden(
    orden_id: int,
    data: dict,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_OPERACION)),
):
    orden = session.get(Orden, orden_id)
    exigir_acceso_a_punto(current_user, orden.punto_id)
    nuevo_estado = data.get("estado")
    orden.estado = OrdenEstado(nuevo_estado)
    if OrdenEstado(nuevo_estado) == OrdenEstado.CANCELADO:
        registrar_auditoria(accion="ANULAR_ORDEN", ...)
```

**¿Puede `TOMADOR_ORDEN` cancelar órdenes? Sí.** `_ROLES_OPERACION` incluye
`tomador_orden` (junto con `cocinero`, `repartidor`, `resp_tienda`,
`gerente_punto`, `gerente_general`, `admin` — `gerente_central` es el único
rol excluido).

**¿Solo las propias? No.** La única validación de pertenencia es
`exigir_acceso_a_punto(current_user, orden.punto_id)` — confirma que la
orden es **de la misma tienda** del usuario, pero no compara
`orden.tomada_por` contra `current_user.user_id`. Cualquier `TOMADOR_ORDEN`
de una tienda puede cancelar **cualquier orden de esa tienda**, la haya
tomado quien la haya tomado.

**¿Qué pasa si cancela una orden ya "cobrada"?** Hoy no existe el concepto
de "cobrada", así que técnicamente la pregunta es "¿qué pasa si cancela una
orden en cualquier estado, incluido `entregado`?" — y la respuesta es:
**nada se lo impide.** No hay ningún guard que bloquee la transición a
`CANCELADO` desde `entregado` ni desde ningún otro estado. Y, el hallazgo
más importante de toda esta auditoría:

> **Cancelar una orden no toca `TransaccionVenta` en absoluto.** Si ya se
> había llamado `POST /api/ordenes/transacciones/` para esa orden (lo normal,
> ya que `NewOrderView` la dispara de inmediato tras crear la orden), esa
> fila de venta se queda con `metodo_pago="efectivo"` y
> `estado="completada"` para siempre. `_calcular_efectivo_esperado()` (§4)
> la sigue sumando como si la venta siguiera en pie. **Hoy es posible que
> el efectivo esperado en el cuadre de caja esté sobreestimado por cada
> orden en efectivo que se cancele después de cobrada.**

---

## 7. Resumen de hallazgos

1. **(Crítico, §0)** `Orden.estado` es la variable de la cocina, no del
   cobro — está consumida por exact-match en 4+ archivos del frontend.
   Agregar `PENDIENTE_RECIBIR`/`COBRADA` como valores nuevos de esa misma
   columna rompe la pantalla de cocina y los contadores del POS.
2. **(Crítico)** Cancelar una orden no actualiza ni toca
   `TransaccionVenta` — una venta en efectivo cancelada sigue contando en
   el cuadre de caja hoy mismo, sin que se haya tocado nada de este
   proyecto. Esto ya es un bug existente, independiente de la nueva
   funcionalidad.
3. `dinero_recibido`/`vuelto` sí se persisten, pero son el cálculo del
   vendedor al crear la orden — no hay ningún paso de confirmación por el
   responsable hoy. Coincide exactamente con el problema que describes.
4. `_calcular_efectivo_esperado()` no filtra por `TransaccionVenta.estado`
   (aunque ese campo nunca tiene otro valor que `"completada"` de todas
   formas) y no mira el estado de la `Orden` asociada en absoluto.
5. El cierre de caja no valida nada sobre órdenes activas — ninguna
   consulta a `Orden` existe en `cerrar_caja()`.
6. `TOMADOR_ORDEN` puede cancelar cualquier orden de su tienda (no solo las
   propias), en cualquier estado (incluido `entregado`), sin ninguna
   restricción hoy.

---

## 8. Pregunta que bloquea empezar Fase 2

**¿`PENDIENTE_RECIBIR` y `COBRADA` van en `Orden.estado` (reemplazando/
ampliando el enum que usa cocina) o en un campo nuevo y separado** (p. ej.
`Orden.estado_cobro`, independiente de `Orden.estado`)?

Mi recomendación, para que no se pierda en el texto: **campo separado**.
Preparar la comida y cobrarla son ejes independientes — una orden puede
estar `preparando` en cocina y `pendiente_recibir` en cobro al mismo
tiempo, y tiene que poder estarlo sin que ninguna de las dos pantallas
(cocina, cobro) tenga que aprender a ignorar valores del enum que no le
importan. Si lo prefieren en el mismo campo por alguna razón que no esté
viendo, dígamelo y ajusto `KitchenView.vue`/`OrdersListView.vue`/
`POSMainView.vue` como parte de la Fase 2, pero quería que la decisión la
tomaran con este hallazgo sobre la mesa, no que se descubriera a medio
implementar.

No implemento nada hasta que respondas esto (y cualquier otra cosa que
quieras ajustar de las "decisiones confirmadas" a la luz de los hallazgos
de §2 y §6).
