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

**Producción**
- Backend y frontend de impresión desplegados. Commit en producción: 755d717.
- Cobro en efectivo verificado: el vendedor registra, el responsable confirma, el cuadre cuenta solo COBRADA.
- Rotación de secretos completada: contraseña de la base, SECRET_KEY, JWT_SECRET y contraseña de admin. Los vendedores deben volver a iniciar sesión.
- Usuarios activos: admin (ADMIN, sin tienda, solo administración), vendedor1 (TOMADOR_ORDEN, Local Centro), alejandro (GERENTE_CENTRAL, sin tienda, sin POS), central_test (desactivado).
- Local Centro: vendedor y responsable creados; flujo de venta en efectivo probado de punta a punta.
- Impresora y cajón de Centro: pendientes de activar por SQL tras la prueba física (ver docs/RUNBOOK_ACTIVAR_CENTRO.md). Jordán y Auxiliar siguen desactivadas.

**Seguridad pendiente**
- El historial de Git fue reescrito (los secretos ya no están en main). Quedan pendientes: solicitud a GitHub Support para purgar los SHA 0c5d690, 64d095e y 0c08f58; revisar alertas de Secret Scanning; revisar forks.
- Hay respaldos con valores viejos en el servidor (/root/). Borrarlos cuando la producción esté estable varios días.

**Reglas aprendidas hoy (obligatorias)**
- Nunca editar .env.production con sed ni reemplazos de texto. Para secretos, usar un script en Python que valide el formato de DATABASE_URL y DATABASE_SYNC_URL (postgresql://usuario:clave@db:5432/foodops_db) antes de escribir, y que pruebe la conexión por TCP desde la red de Docker antes de recrear api.
- Una conexión psql por socket local dentro del contenedor no valida la contraseña (pg_hba usa trust para local). Validar siempre por TCP desde la red de Docker.
- Un bloqueo por intentos fallidos aparece en la tabla usuarios (intentos_fallidos, bloqueado_hasta). Revisarlo antes de suponer que la contraseña está mal.
- Un usuario de rol multitienda sin punto_id no puede operar POS. Los vendedores deben tener punto_id; admin no se usa para vender.
- El formato de .env.production y las URLs se verifican antes de reiniciar cualquier servicio.

**Pendiente de decisión**
- Si admin debe poder vender (requiere selector de tienda en el POS) o solo administrar (recomendado).
- Confirmar el rol de alejandro.
- Code page de la impresora AON PR-350WF (prueba_impresora.py, pendiente de resultado en Centro).
- Responsables y vendedores de Jordán y Auxiliar.
