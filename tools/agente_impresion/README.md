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
- **Imprimió pero no pudo reportar** (red caída): el agente recuerda el
  resultado y, si el backend se lo vuelve a entregar, lo reporta sin
  imprimir otra vez (no duplica tickets ni abre el cajón dos veces).
- Los textos de la orden se limpian de caracteres de control antes de
  imprimir: un nombre o nota no puede inyectar comandos a la impresora.

## Pruebas

`tests/unit/test_agente_impresion.py`, con impresora mock (en memoria y un
servidor TCP en 127.0.0.1). Ninguna prueba toca una impresora real.

## Pendiente (fase de empaquetado)

Ejecutable Windows (`pyinstaller`), instalación como servicio y arranque
automático.
