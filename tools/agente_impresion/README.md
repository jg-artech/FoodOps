# Agente de impresión de tienda

Programa que corre en la PC de cada tienda. Cada pocos segundos le pregunta
al backend de FoodOps si hay trabajos de impresión para su tienda, los manda
a la impresora térmica por la red local (ESC/POS, puerto 9100) y reporta el
resultado. Diseño completo: `docs/DISENO_IMPRESION.md`.

Hace falta porque el backend (en la nube) no puede alcanzar la IP privada
de la impresora, y el navegador no puede abrir un socket TCP crudo.

- Solo biblioteca estándar de Python 3.10+ (sin `pip install`).
- Dos tipos de trabajo: `ticket` (JSON de la orden → ESC/POS) y
  `abrir_cajon` (pulso `1B 70 00 19 FA`, probado en la AON PR-350WF).
- El backend nunca manda HTML: el agente arma los bytes a partir del JSON.

## Configuración (solo variables de entorno)

| Variable | Obligatoria | Default | Qué es |
|---|---|---|---|
| `FOODOPS_API_URL` | sí | | URL base del backend, p. ej. `https://foodops.ejemplo.com` |
| `FOODOPS_AGENTE_TOKEN` | sí | | Token de la tienda (ver abajo). Secreto: no lo pegue en chats ni en el repo. |
| `FOODOPS_IMPRESORA_IP` | sí | | IP de la impresora en la red local de la tienda |
| `FOODOPS_IMPRESORA_PUERTO` | no | `9100` | Puerto ESC/POS |
| `FOODOPS_POLL_SEGUNDOS` | no | `5` | Cada cuánto pregunta al backend (recomendado 5–10) |
| `FOODOPS_TIMEOUT_SOCKET` | no | `5` | Timeout de conexión a la impresora (s) |
| `FOODOPS_TIMEOUT_HTTP` | no | `10` | Timeout de cada request al backend (s) |
| `FOODOPS_ANCHO_COLUMNAS` | no | `42` | Caracteres por línea (42 para papel de 80 mm, 32 para 58 mm) |
| `FOODOPS_NOMBRE_NEGOCIO` | no | `Asados a la Leña` | Encabezado del ticket |
| `FOODOPS_ARCHIVO_IMPRESOS` | no | Windows: `%LOCALAPPDATA%\FoodOpsAgente\impresos.json`; otros: `~/.local/state/foodops-agente/impresos.json` | Registro local de trabajos ya impresos (ver "No reimprimir tras un reinicio"). Debe quedar fuera del repo y de la carpeta del ejecutable. |

## Token de la tienda

Lo genera un `admin` o `gerente_general`:

```
POST /api/puntos-venta/{punto_id}/regenerar-token-agente
```

La respuesta trae el token **una sola vez**: el backend solo guarda su
sha256. Si se pierde o se filtra, se regenera: el anterior queda revocado
al instante y el agente que lo use empieza a recibir 401 (lo registra en el
log y reintenta cada 60 s hasta que se actualice la variable).

## Ejecutar

Desde la carpeta `tools/`:

```
cd tools
python -m agente_impresion
```

## Activar una tienda

En `puntos_venta` (hoy por SQL; no hay pantalla todavía):

- `impresora_activa = true`: el backend acepta trabajos `ticket` de esa
  tienda. Con `false`, `POST /api/impresion/ticket` responde 409 y el
  frontend sigue usando `window.print()`.
- `cajon_activo = true`: `confirmar-cobro` encola la apertura automática del
  cajón y se habilita el botón manual. Con `false` nunca se genera
  `abrir_cajon` para esa tienda.

## Comportamiento ante fallos

- **Agente apagado**: los trabajos quedan `pendiente` y se imprimen cuando
  vuelva. La venta nunca se bloquea.
- **Impresora falla** (sin papel, apagada): el trabajo queda en `error` con
  el detalle, y se puede reintentar desde el sistema.
- **El agente se cae a media impresión**: a los 30 s el backend vuelve a
  entregar el trabajo.
- **Imprimió pero no pudo reportar** (red caída o reinicio del agente): ver
  la sección siguiente.
- **Apertura de cajón vieja**: un `abrir_cajon` creado hace más de 120 s ya
  no se entrega; el backend lo marca `error = "caducado"` y el agente nunca
  recibe el pulso.
- Los textos de la orden se limpian de caracteres de control antes de
  imprimir: un nombre o nota no puede inyectar comandos a la impresora.

## No reimprimir tras un reinicio

El backend reentrega a los 30 s un trabajo que no recibió resultado (para
no perderlo si el agente se cae antes de imprimir). Para que eso no duplique
un ticket ni vuelva a abrir el cajón, el agente guarda en
`FOODOPS_ARCHIVO_IMPRESOS` el id de cada trabajo impreso con éxito,
**después de imprimir y antes de reportar** (escritura atómica). Si recibe
un id que ya está ahí, solo reporta `ok`, sin imprimir.

Los trabajos que fallaron no se registran: si alguien los reintenta desde
el sistema, se vuelven a imprimir. El archivo guarda los últimos 5000 ids.
Queda una ventana mínima sin cubrir: si el proceso muere justo entre el
envío a la impresora y la escritura del archivo, ese trabajo se imprime
otra vez.

## Pruebas

`tests/unit/test_agente_impresion.py`, con impresora mock (en memoria y un
servidor TCP en 127.0.0.1). Ninguna prueba toca una impresora real.

## Pendiente (fase de empaquetado)

Ejecutable Windows (`pyinstaller`), instalación como servicio y arranque
automático.
