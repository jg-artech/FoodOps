# Runbook: activar la impresión por agente en Local Centro

Pasos para pasar una tienda de `window.print()` a impresión por agente
(ticket + cajón). Escrito para Local Centro, válido para cualquier tienda.
Diseño: `docs/DISENO_IMPRESION.md`. Agente: `tools/agente_impresion/README.md`.

**Todos los comandos de este documento los ejecuta Jorge a mano.** Ni el
agente ni Claude los ejecutan. Ningún valor real va en este archivo: se
usan marcadores.

| Marcador | Qué es |
|---|---|
| `<ID_TIENDA>` | `id` de la tienda en `puntos_venta` (consúltelo, no lo asuma) |
| `<SERVIDOR>` | Acceso SSH al servidor de producción |
| `<URL_API>` | URL base del backend de producción |
| `<JWT_ADMIN>` | Sesión de un usuario `admin` o `gerente_general` (ver paso 0.2) |
| `<IP_IMPRESORA>` | IP fija de la impresora en la red de la tienda |

Las consultas SQL se ejecutan en el servidor así:

```
ssh <SERVIDOR>
docker exec foodops-db psql -U foodops_user -d foodops_db -c "<SQL>"
```

Las fechas de `tokens_agente` y `trabajos_impresion` se guardan en UTC sin
zona; por eso las consultas comparan con `now() at time zone 'utc'`.

> ⚠️ **Cambio para el personal en cuanto se active la impresora (paso 2):**
> en esa tienda, el ticket de una orden **en efectivo** ya no se imprime al
> crear la orden. Se imprime desde **Cobros pendientes → Imprimir ticket**,
> después de que el responsable confirme el cobro. Tarjeta y transferencia
> se imprimen igual que antes, al cobrar. Avíseles antes del paso 2.

---

## Paso 0. Preparación (una sola vez)

### 0.1 Identificar la tienda

```sql
select id, nombre, impresora_activa, cajon_activo from puntos_venta order by id;
```

**Esperado:** la tienda aparece con `impresora_activa = f` y `cajon_activo = f`.
Anote su `id`: es `<ID_TIENDA>` en el resto del documento.
**Si falla** (la tienda ya está en `t`): no siga; averigüe quién la activó.

### 0.2 Generar el token del agente

No hay pantalla para esto. Inicie sesión en la app con un usuario `admin` o
`gerente_general`, copie el token de sesión (DevTools → Application →
Local Storage → `token`) y, desde su propia computadora:

```
curl -s -X POST "<URL_API>/api/puntos-venta/<ID_TIENDA>/regenerar-token-agente" \
     -H "Authorization: Bearer <JWT_ADMIN>"
```

**Esperado:** JSON con `token`. **Se muestra una sola vez**: cópielo
directo a la variable de entorno del paso 0.3, sin pegarlo en chats,
correos ni archivos. Si se pierde, se regenera (el anterior queda revocado).
**Si falla:** 401 → la sesión expiró, vuelva a iniciar sesión; 403 → el
usuario no es `admin` ni `gerente_general`.

### 0.3 Configurar la PC de la tienda

1. Python 3.10 o superior instalado (`python --version`).
2. Copiar la carpeta `tools\agente_impresion` a la PC (por ejemplo
   `C:\FoodOps\tools\agente_impresion`).
3. La impresora tiene IP fija y responde en el puerto 9100 desde la PC:
   `Test-NetConnection <IP_IMPRESORA> -Port 9100` → `TcpTestSucceeded : True`.
4. Variables de entorno **de la cuenta de usuario** (Inicio → "Editar las
   variables de entorno de su cuenta"):
   - `FOODOPS_API_URL` = `<URL_API>`
   - `FOODOPS_AGENTE_TOKEN` = el token del paso 0.2
   - `FOODOPS_IMPRESORA_IP` = `<IP_IMPRESORA>`
   - Opcionales: ver la tabla del README del agente.
5. Cerrar y abrir PowerShell para que tome las variables nuevas.

**Si falla:** sin Python → instálelo (marque "Add python.exe to PATH");
`TcpTestSucceeded : False` → revise IP, cable/Wi-Fi y que la impresora esté
encendida antes de seguir.

---

## Paso 1. Verificación previa: el agente corre a mano

En la PC de la tienda:

```
cd C:\FoodOps\tools
python -m agente_impresion
```

Déjelo corriendo. En el servidor (solo lectura):

```sql
select punto_id, activo, created_at, revocado_at, ultima_conexion_at,
       round(extract(epoch from (now() at time zone 'utc') - ultima_conexion_at)) as seg_desde_conexion
from tokens_agente
where punto_id = <ID_TIENDA>
order by created_at;
```

**Esperado:**
- La consola del agente muestra `Agente iniciado: ...` y ningún error.
- Exactamente una fila con `activo = t` y `revocado_at` vacío.
- `seg_desde_conexion` menor que 10, y baja cada vez que repite la consulta.
- En la app, Caja o Cobros pendientes de esa tienda muestran
  **"Agente conectado"**.

**Si falla:**
- `Faltan variables de entorno` → paso 0.3.
- `El backend rechazó el token` → token mal copiado o revocado: repita 0.2.
- `Sin conexión con el backend` → revise internet en la PC y `<URL_API>`.
- `ultima_conexion_at` vacío → el agente no está llegando al backend.

Todavía no se imprime nada: la tienda sigue con `impresora_activa = false`.

---

## Paso 2. Activar solo la impresora (sin cajón)

```sql
update puntos_venta set impresora_activa = true, cajon_activo = false
where id = <ID_TIENDA>;
select id, nombre, impresora_activa, cajon_activo from puntos_venta where id = <ID_TIENDA>;
```

**Prueba:** con el agente corriendo, cree en la app una orden pagada con
**tarjeta** en esa tienda y pulse **Imprimir ticket**.

**Esperado:**
- La app muestra "Ticket enviado a impresora" y, a los pocos segundos,
  "Ticket impreso". **No** se abre el diálogo de impresión del navegador.
- La impresora imprime el ticket con los datos correctos (tildes y ñ
  incluidas, ancho correcto).
- En el servidor:

```sql
select id, tipo, estado, error, created_at, completado_at
from trabajos_impresion where punto_id = <ID_TIENDA>
order by id desc limit 5;
```

  El último trabajo es `ticket` con `estado = ok`.

**Si falla:**
- `estado = error` con detalle de conexión → la PC no alcanza la impresora
  (repita `Test-NetConnection`); use **Reintentar** desde la app.
- Se queda en `pendiente` → el agente no está corriendo (paso 1).
- Texto cortado o desalineado → ajuste `FOODOPS_ANCHO_COLUMNAS` (42 para
  80 mm, 32 para 58 mm) y reinicie el agente.
- Cualquier problema que no se resuelva en el momento → **ROLLBACK** (al
  final): la tienda vuelve a `window.print()` de inmediato.

---

## Paso 3. Activar el cajón

Solo si el cajón está conectado por RJ11 a la impresora.

```sql
update puntos_venta set cajon_activo = true where id = <ID_TIENDA>;
select id, nombre, impresora_activa, cajon_activo from puntos_venta where id = <ID_TIENDA>;
```

**Prueba:** con un usuario `resp_tienda` (o gerencia) de esa tienda, en
**Cobros pendientes → Abrir cajón**, escriba un motivo de 5 o más
caracteres (por ejemplo "prueba de cajón") y confirme.

**Esperado:**
- La app muestra "Cajón abierto" y la gaveta se abre una vez.
- Con un motivo de menos de 5 caracteres la app no envía nada.
- Un `tomador_orden` no ve el botón.
- En el servidor, el trabajo `abrir_cajon` queda en `ok`:

```sql
select id, tipo, estado, error, motivo, created_at
from trabajos_impresion where punto_id = <ID_TIENDA> and tipo = 'abrir_cajon'
order by id desc limit 5;
```

**Prueba adicional (recomendada):** confirme un cobro en efectivo en Cobros
pendientes → la gaveta se abre sola **una vez**; reimprimir el ticket no la
vuelve a abrir.

**Si falla:**
- "El cajón no está configurado para esta tienda" → el `update` no se
  aplicó; repítalo.
- `estado = ok` pero la gaveta no abre → cable RJ11 o cajón; vuelva a
  `cajon_activo = false` mientras se revisa.
- `error = caducado` → el agente tardó más de 120 s en recogerlo (estaba
  apagado o sin red): es lo esperado, use el botón otra vez.

---

## Paso 4. Reinicio de la PC: el agente vuelve solo

Instale la tarea programada (una vez), con la misma cuenta de Windows que
tiene las variables de entorno:

```
cd C:\FoodOps\tools\agente_impresion
powershell -ExecutionPolicy Bypass -File .\instalar_tarea.ps1
```

**Esperado del script:** `OK` para cada variable (solo nombres), la versión
de Python y "Tarea 'FoodOpsAgenteImpresion' instalada". Cierre el agente
que corría a mano y **reinicie la PC**. Tras iniciar sesión:

```sql
select punto_id, activo,
       round(extract(epoch from (now() at time zone 'utc') - ultima_conexion_at)) as seg_desde_conexion
from tokens_agente where punto_id = <ID_TIENDA> and activo;
```

**Esperado:** `seg_desde_conexion` menor que 10 sin que nadie haya
arrancado el agente; "Agente conectado" en la app; una orden con tarjeta
imprime.

**Si falla:**
- El script dice que faltan variables → están en la sesión, no en la
  cuenta: defínalas como en 0.3.
- El script no encuentra Python o encuentra el de la Store → use
  `-PythonExe "C:\ruta\python.exe"`.
- La tarea existe pero el agente no corre → `Get-ScheduledTask -TaskName
  FoodOpsAgenteImpresion | Get-ScheduledTaskInfo` y revise
  `%LOCALAPPDATA%\FoodOpsAgente\agente.log`.
- Tras el reinicio nadie inicia sesión → la tarea arranca **al iniciar
  sesión**: configure el inicio de sesión automático de Windows o pida que
  alguien inicie sesión al encender.
- El script **no está probado en Windows**: si falla de una forma no
  descrita aquí, desinstale con `-Desinstalar`, siga con el agente a mano y
  reporte el error.

---

## Paso 5. Prueba desde un móvil Android de un vendedor

Requisito: Cloudflare purgado tras el último despliegue de frontend (si no,
el móvil puede seguir con la versión vieja de la app).

Con el móvil Android de un vendedor (`tomador_orden`) de esa tienda:

1. Abra la app (si ya estaba instalada como app, ciérrela y ábrala; debe
   recargarse sola con la versión nueva).
2. Cree una orden con **tarjeta** y pulse Imprimir ticket.
3. Cree una orden en **efectivo** y pulse Imprimir ticket.

**Esperado:**
- Tarjeta: "Ticket enviado a impresora" y el ticket sale por la impresora
  de la tienda, sin diálogo de impresión en el móvil.
- Efectivo: mensaje "El cobro aún no ha sido confirmado por el
  responsable…", sin imprimir y sin diálogo; aparece el aviso "El cajón lo
  abre el responsable de la tienda". Tras confirmar el cobro en Cobros
  pendientes, el responsable imprime el ticket desde ahí.
- El vendedor no ve ningún botón de Abrir cajón.

**Si falla:**
- Se abre el diálogo de impresión del móvil → la tienda sigue con
  `impresora_activa = false` o el móvil tiene la app vieja (purgue
  Cloudflare, cierre y abra la app).
- "No tienes permiso para imprimir este ticket" → el usuario no es de esa
  tienda o no tiene un rol de impresión.

Cancele las órdenes de prueba al terminar.

---

## ROLLBACK completo

Vuelve la tienda a `window.print()` en el acto, sin tocar ventas ni cobros.
**Lo ejecuta Jorge a mano, no el agente.**

1. Desactivar impresora y cajón:

```sql
update puntos_venta set impresora_activa = false, cajon_activo = false
where id = <ID_TIENDA>;
```

2. Revocar el token del agente (deja de autenticarse al instante; queda el
   historial):

```sql
update tokens_agente
set activo = false, revocado_at = (now() at time zone 'utc')
where punto_id = <ID_TIENDA> and activo = true;
```

3. Cerrar los trabajos que quedaron en cola, para que no se impriman ni
   abran el cajón si la tienda se reactiva más adelante (recomendado):

```sql
update trabajos_impresion
set estado = 'error', error = 'rollback', completado_at = (now() at time zone 'utc')
where punto_id = <ID_TIENDA> and estado in ('pendiente', 'imprimiendo');
```

4. Verificar:

```sql
select id, nombre, impresora_activa, cajon_activo from puntos_venta where id = <ID_TIENDA>;
select count(*) filter (where activo) as tokens_activos from tokens_agente where punto_id = <ID_TIENDA>;
select estado, count(*) from trabajos_impresion where punto_id = <ID_TIENDA> group by estado;
```

   **Esperado:** `f`/`f`, `tokens_activos = 0`, nada en `pendiente` ni
   `imprimiendo`.

5. En la PC de la tienda: `powershell -ExecutionPolicy Bypass -File
   .\instalar_tarea.ps1 -Desinstalar` y cerrar la consola del agente.

Para volver a activar después de un rollback se empieza desde el paso 0.2
(token nuevo).
