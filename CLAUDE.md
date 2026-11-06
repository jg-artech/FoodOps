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
- Un vendedor nunca abre el cajón ni cancela una orden COBRADA.
- La venta nunca depende de que el agente o la impresora funcionen.
- Un trabajo ABRIR_CAJON caduca a los 120 segundos y se crea una sola vez por orden.

## Impresión
- Diseño: docs/DISENO_IMPRESION.md (fuente de verdad). Leerlo antes de tocar impresión o cobro.
- Agente de tienda: tools/agente_impresion/ (Python, corre en Windows). Documentación en tools/agente_impresion/README.md.
- Impresora: AON PR-350WF, papel de 80 mm, ESC/POS por TCP, puerto 9100 por defecto.
- Pulso del cajón: bytes 0x1B 0x70 0x00 0x19 0xFA.
- Mientras una tienda tenga impresora_activa = false, el ticket se imprime con window.print() desde el navegador. Esta excepción transitoria está documentada en la sección 7 del diseño.
- Code page: pendiente de confirmar con tools/agente_impresion/prueba_impresora.py. Hoy el texto impreso sale mal con ñ, acentos y el símbolo €.

## Infraestructura (sin secretos)
- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL 15 en Docker. Servicios de compose: db y api.
- Frontend: Vue 3, Vite, Pinia. El build sale de foodops-web/dist y se sube al servidor, donde nginx lo sirve.
- Las direcciones del servidor, las IPs y los dominios de producción están en la documentación de despliegue, no aquí. No los copies a ningún archivo del repositorio.
- No hagas SSH, curl ni consultas SQL contra producción, salvo que Jorge lo pida de forma explícita para esa tarea.
- Migración más reciente: 012_impresion_agente.

## Reglas de trabajo
- No hagas git push. Jorge lo hace a mano.
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
- Cobro en efectivo: desplegado en producción y verificado.
- Impresión (backend y frontend): desplegada en producción. Las tres tiendas siguen con impresora_activa = false y cajon_activo = false.
- Local Centro: agente instalado en la PC de la tienda. Pendiente: verificar la tarea programada (reintento y reinicio), activar la impresora por SQL y probar desde un móvil Android.
- Pendiente de decisión: code page de la impresora. Se resuelve con tools/agente_impresion/prueba_impresora.py.
- Pendiente de push: cinco commits locales, el último es 0be9569.
