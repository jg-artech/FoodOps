# FoodOps: contexto para Claude Code

## Negocio
Restaurante "Asados a la Leña" con 3 tiendas: Local Centro (id 2), Local Jordán (id 8) y Local Auxiliar (id 9). Varias tiendas operan al mismo tiempo, cada una con sus vendedores, caja, inventario y cocina.

## Roles reales (base de datos y código)
- TOMADOR_ORDEN: vendedor. Registra órdenes y cobros, pero no confirma efectivo ni abre cajón.
- RESP_TIENDA: responsable de tienda.
- GERENTE_PUNTO: gerente de tienda.
- GERENTE_GENERAL y ADMIN: administración.
- GERENTE_CENTRAL: solo abastecimiento, sin POS.
- REPARTIDOR, COCINERO, BODEGUERO: sin acceso a caja ni a impresión de cobros.

## Reglas de negocio (no se negocian)
- El vendedor registra el cobro en efectivo como orden en estado PENDIENTE_RECIBIR.
- Solo quien tiene permiso de ROLES_ABRIR_CAJON confirma la recepción con POST /api/ordenes/{id}/confirmar-cobro. El efectivo entra al cuadre únicamente cuando la orden está COBRADA.
- No existe efectivo sin orden: POST /api/ordenes/transacciones/ responde 400 si metodo_pago es efectivo y no hay orden_id.
- El cierre de caja se bloquea si hay órdenes PENDIENTE_RECIBIR.
- Un vendedor no abre el cajón ni cancela ninguna orden.
- La venta nunca depende de que el agente o la impresora funcionen.
- Un trabajo ABRIR_CAJON caduca a los 120 segundos y se crea una sola vez por orden.
- Cancelar una orden requiere motivo y la contraseña personal de quien cancela. El intento fallido cuenta en el bloqueo del login.
- Solo se cancela por POST /api/ordenes/{id}/cancelar-cocina (Cocina) o POST /api/ordenes/{id}/cancelar (Órdenes). PUT /api/ordenes/{id}/status con estado cancelado responde 409 a todos los roles, y una orden cancelada no se reactiva.
- Órdenes pendientes: pueden cancelarse desde Órdenes o Cocina por responsable, gerente de punto, gerente general o admin. El vendedor no cancela; se lo pide al responsable.
- Órdenes pagadas: pueden cancelarse desde Órdenes, pero la devolución al cliente NO existe todavía. Hasta que exista, la caja queda con sobrante. Regla operativa: no cancelar órdenes pagadas; devolver por el método manual y dejar la orden como está.
- No se cancela una orden pagada de un día con caja cerrada. (Regla vigente; implementación pendiente.)
- La devolución de dinero será un movimiento propio ligado a la orden, nunca un cambio de estado del cobro original.

## Cocina: personal y responsable por orden (migración 016)
- El personal de cocina es un catálogo por tienda (tabla personal_cocina), sin vínculo con los usuarios del sistema. No se borra: se desactiva.
- Lo administran resp_tienda (solo su tienda), gerente_general y admin, en /config/personal-cocina. gerente_punto no lo administra.
- Cada orden tiene un responsable de cocina. El cocinero elige a cualquier persona activa de su tienda solo si la orden aún no tiene responsable; reasignar es de resp_tienda, gerente_punto, gerente_general y admin.
- La primera asignación pasa la orden de pendiente a preparando y guarda en_preparacion_at. Cada cambio queda en auditoría con antes y después.
- No se cambia el responsable con la orden en listo, entregado o cancelado (409).
- Sin responsable no se marca listo ni entregado (409). Excepción: órdenes anteriores a la migración 016 (exige_responsable_cocina = false).
- Si una tienda no tiene personal activo, Cocina no puede marcar LISTO: cargar el personal antes de operar una tienda nueva.

## Menú: productos y categorías (migraciones 015 y 017)
- Las categorías viven en la tabla categorias_menu, no en el navegador. productos_menu.categoria guarda la clave, que no cambia; nombre, emoji y posición sí.
- Nueva orden muestra las categorías activas en el orden de posición (gerencia lo cambia con ▲ ▼ en Configuración → Menú) y oculta las que no tienen productos. Dentro de cada categoría, los productos van del precio menor al mayor (cambio pedido el 2026-11-26; antes era de mayor a menor).
- Orden inicial: Combos, Costillas, Pollos, Guarniciones, Bebidas, Extras. "Pollo por piezas" se creó inactiva para que el POS siguiera igual que antes (nunca aparecía en Nueva orden). Antes de activarla, revisar para qué se usan sus productos (Pechuga y Ala, Cuadril y Pierna).
- Categorías y productos no se borran de la base: se desactivan. Una categoría con productos activos no se desactiva (409). Eliminar un producto (✕ en Configuración) lo deja con activo = false; las órdenes guardan nombre y precio, y no hay botón para reactivarlo.
- Solo gerente_general y admin administran el menú y las categorías; cualquier rol las lee.
- Items de inventario: se administran en Configuración → Inventario (gerente_general y admin). Catálogo de empresa (punto_id NULL), agrupado por tipo: vendible, insumo, desechable. orden_conteo define el orden del Inventario Diario dentro de cada tipo. Nombre único sin importar mayúsculas. No se borran: se desactivan, y no se desactiva un item que esté en la receta de un producto activo (409). Para que una venta descuente un item, se agrega a la receta del producto (🧩); el selector de la receta agrupa los items por tipo.
- En "Personalizar" (combos), los grupos elegibles salen en el orden de su número de grupo en la receta (grupo 1 arriba). Para cambiar ese orden se ajusta el número de grupo en la receta.

## Impresión
- Diseño: docs/DISENO_IMPRESION.md (fuente de verdad). Leerlo antes de tocar impresión o cobro.
- Agente de tienda: tools/agente_impresion/ (Python, corre en Windows). Documentación en tools/agente_impresion/README.md.
- Impresora: AON PR-350WF, papel de 80 mm, ESC/POS por TCP, puerto 9100 por defecto.
- Pulso del cajón: bytes 0x1B 0x70 0x00 0x19 0xFA.
- Mientras una tienda tenga impresora_activa = false, el ticket se imprime con window.print() desde el navegador. Esta excepción transitoria está documentada en la sección 7 del diseño.
- Code page: CP858 (ESC t 19, codificación cp858), precedido de FS . (0x1C 0x2E) para cancelar el modo chino. Validado en papel en Centro el 2026-11-22, con prueba_impresora.py y con un ticket de venta real: ñ, acentos, ¡ y € salen bien. Reemplaza a CP850 (ESC t 2), que se probó el 2026-11-21 y no tiene €.
- Requisito de la impresora: el modo chino debe estar desactivado en el panel (DIP "Chinese mode" = NO). Si se resetea la impresora, revisar este ajuste. El agente igual envía FS . en cada ticket.
- Corte al final del ticket: ESC d 4 + GS V 0 (0x1B 0x64 0x04 0x1D 0x56 0x00). Validado en la AON PR-350WF de Centro. El trabajo abrir_cajon no avanza ni corta.
- Cortador trabado: la impresora puede marcar "cutter stuck". Procedimiento: FEED o reinicio de la impresora; si no destraba, girar el engranaje de la tapa indicada.
- Prueba de code page en la PC de la tienda: python -m agente_impresion.prueba_impresora --ip <IP_IMPRESORA> desde tools/.
- Prueba física del ticket del agente, sin backend ni token: python3 -m agente_impresion.prueba_corte --ip <IP_IMPRESORA> desde tools/ (también funciona desde WSL).
- Ticket completo del agente confirmado en la PC del POS de Centro (2026-11-21, Python 3.13 del usuario Usuario, prueba_corte desde C:\FoodOpsAgente\tools): "Leña", "Atendió" y "¡Gracias por su compra!" salen bien; el ticket normal avanza y corta, y el de control (--sin-corte) no corta. Las variantes de corte también se probaron; el agente sigue usando la A (ESC d 4 + GS V 0).
- Impresión por navegador en Centro: Windows usa el driver "Generic / Text Only", que no corta y avanza una hoja completa. No se arregla desde ticket.js (se intentó y se revirtió); requiere instalar el driver POS-80 por TCP/IP o activar el agente.

## Infraestructura (sin secretos)
- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL 15 en Docker. Servicios de compose: db y api.
- Frontend: Vue 3, Vite, Pinia. El build sale de foodops-web/dist y se sube al servidor, donde nginx lo sirve.
- Las direcciones del servidor, las IPs y los dominios de producción están en la documentación de despliegue, no aquí. No los copies a ningún archivo del repositorio.
- No hagas SSH, curl ni consultas SQL contra producción, salvo que Jorge lo pida de forma explícita para esa tarea.
- Migración más reciente: 017_categorias_menu (local y producción).

## Reglas de trabajo
- No hagas git push ni despliegues sin aprobación explícita de Jorge en el mensaje actual. Sin esa aprobación, Jorge lo hace a mano.
- No leas archivos .env*, respaldos .bak, tokens ni credenciales. No imprimas URLs de conexión ni secretos en la salida.
- No modifiques foodops-web/dev-dist/sw.js.
- No generes tokens del agente ni hagas login contra producción.
- Haz commits locales por tema, con mensaje convencional (feat:, fix:, docs:, test:, refactor:). Muestra el diff antes de cada commit.
- Antes de cambiar código de impresión o de cobro, lee docs/DISENO_IMPRESION.md.
- Si una prueba falla, repórtalo. No la desactives ni la marques como omitida para que pase.
- Los cambios de impresión deben mantener la suite de pytest en verde.
- Los documentos en docs/AUDITORIA_*.md son históricos. No son fuente de verdad.
- Las pruebas del agente de Windows no se pueden ejecutar desde este entorno. Indícalo en vez de simular el resultado.

## Estado al cierre de la última sesión

**Producción**
- Commit en producción: backend 65a627c y frontend 1ca331d (2026-11-26), migración 017; bundle index-7d046450.js → index-8a4f9906.js. Validado en local por Jorge; falta validarlo en producción. El servidor (/opt/FoodOps) sigue en 65a627c: el frontend se sube con rsync y no depende del git del servidor.
- Montos en quetzales: el frontend formatea todos los importes con formatQ() de foodops-web/src/utils/moneda.js (Q1,234.50, -Q5.00). No usar "$", toFixed a mano ni Intl con GTQ. El ticket (utils/ticket.js) mantiene su propio formato con Q.
- Tras desplegar frontend, purgar Cloudflare; los navegadores con la PWA abierta pueden necesitar cerrar y volver a abrir.
- Cobro en efectivo verificado: el vendedor registra, el responsable confirma, el cuadre cuenta solo COBRADA.
- Rotación de secretos completada para la contraseña de la base y la de admin. SECRET_KEY y JWT_SECRET siguen pendientes de rotar.
- Usuarios activos: admin (ADMIN, sin tienda, solo administración), vendedor1 (TOMADOR_ORDEN, Local Centro), alejandro (GERENTE_CENTRAL, sin tienda, sin POS), central_test (desactivado).
- Local Centro: vendedor y responsable creados; flujo de venta en efectivo probado de punta a punta.
- Centro (tienda id 2): impresora_activa = true, cajon_activo = false. El cajón no se ha comprado: no activarlo. Jordán y Auxiliar siguen desactivadas (ver docs/RUNBOOK_ACTIVAR_CENTRO.md).

- En producción desde 2026-11-07: facturación fase 1 (nombre obligatorio y datos fiscales), cargo de entrega con tope por tienda (Q200.00 en las 3 tiendas) y cancelación con motivo y contraseña en Órdenes y Cocina.
- En producción desde 2026-11-16: rol tomador_orden con permisos por acción, importes de órdenes ajenas ocultos al vendedor, numero_orden sin colisiones y día local único para listado y caja.
- En producción desde 2026-11-24: contenido del producto como campo único (migración 015); la columna descripcion sigue existiendo pero la API no la usa.
- En producción desde 2026-11-26: personal de cocina y responsable por orden (migración 016). Las 34 órdenes previas quedaron con exige_responsable_cocina = false.
- En producción desde 2026-11-26 (d7fc598): eliminar producto del menú con borrado lógico, y categorías en la base con posición configurable (migración 017). Validado por Jorge.
- En producción desde 2026-11-26 (65a627c): pestaña Inventario en Configuración para mantener los items de inventario.
- En producción desde 2026-11-26 (1ca331d, solo frontend): selector de componentes agrupado por tipo, grupos de Personalizar en el orden de la receta y productos de menor a mayor precio.
- Agente de impresión en Centro: imprime tickets de venta reales con CP858 y corte (2026-11-22). escpos.py se instala a mano en cada tienda; Jordán y Auxiliar no lo tienen.

**Seguridad pendiente**
- El historial de Git fue reescrito (los secretos ya no están en main). Quedan pendientes: solicitud a GitHub Support para purgar los commits anteriores a 755d717; revisar alertas de Secret Scanning; revisar forks.
- Hay respaldos con valores viejos en el servidor (/root/). Borrarlos cuando la producción esté estable varios días. Incluye /root/frontend-dist-previo-20261106 (frontend anterior al cambio a Q) y /root/frontend-dist-previo-20261107 (frontend anterior al despliegue de 4bff6c2).
- Respaldo de la base previo a las migraciones 013 y 014: /root/backups/ en el servidor y ~/respaldos-foodops/ en la máquina local. Contiene datos de producción: borrarlo junto con los demás respaldos.
- Respaldos posteriores en /root/, también con datos de producción: backup_pre_lote_20261116_0702.sql.gz, env_pre_lote.bak y frontend-dist-pre-lote/ (2026-11-16); backup_pre_contenido_20261124_0548.sql.gz y env_pre_contenido.bak (2026-11-24); backup_pre_personal_cocina_20261126_0033.sql.gz y frontend-dist-pre-personal-cocina/ (2026-11-26, con copia en ~/respaldos-foodops/); backup_pre_categorias_20261126_0156.sql.gz y frontend-dist-pre-categorias/ (2026-11-26, con copia en ~/respaldos-foodops/); backup_pre_items_20261126_0219.sql.gz y frontend-dist-pre-items/ (2026-11-26, con copia en ~/respaldos-foodops/); frontend-dist-pre-selector/ (2026-11-26, frontend index-7d046450.js). Borrarlos con los demás.
- Deuda de Cloudflare: la regla "Agente impresion" deja pasar /api/impresion/agente/* sin verificar el token en Cloudflare (Skip de Browser Integrity Check). El backend sí valida el token en cada petición. Pendiente: endurecer la regla cuando el plan lo permita, o exigir un header.

**Reglas aprendidas hoy (obligatorias)**
- Nunca editar .env.production con sed ni reemplazos de texto. Para secretos, usar un script en Python que valide el formato de DATABASE_URL y DATABASE_SYNC_URL (postgresql://usuario:clave@db:5432/foodops_db) antes de escribir, y que pruebe la conexión por TCP desde la red de Docker antes de recrear api.
- Una conexión psql por socket local dentro del contenedor no valida la contraseña (pg_hba usa trust para local). Validar siempre por TCP desde la red de Docker.
- Un bloqueo por intentos fallidos aparece en la tabla usuarios (intentos_fallidos, bloqueado_hasta). Revisarlo antes de suponer que la contraseña está mal.
- Un usuario de rol multitienda sin punto_id no puede operar POS. Los vendedores deben tener punto_id; admin no se usa para vender.
- El formato de .env.production y las URLs se verifican antes de reiniciar cualquier servicio.

**Pendiente de decisión**
- Si admin debe poder vender (requiere selector de tienda en el POS) o solo administrar (recomendado).
- Confirmar el rol de alejandro.
- Responsables y vendedores de Jordán y Auxiliar.
- Rotación de JWT_SECRET y SECRET_KEY (ver documentación de despliegue).

**Pendientes**
- Devolución de órdenes pagadas (diseño pendiente).
- Órdenes activas antiguas en cocina (ORD-9 de hace casi 20 días): pueden cerrarse sin responsable; falta decidir si se cierran o se cancelan.
- Huecos en los estados de la orden: PUT /status no valida transiciones ni deja auditoría; se puede marcar entregada una orden sin pagar; POST /cancelar acepta órdenes en listo o entregado.
