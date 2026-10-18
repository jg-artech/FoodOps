#Requires -Version 5.1
<#
.SYNOPSIS
    Instala (o reemplaza) la tarea programada que arranca el agente de
    impresión de FoodOps al iniciar sesión el usuario actual.

.DESCRIPTION
    - Tarea: "FoodOpsAgenteImpresion", disparada al iniciar sesión del
      usuario que ejecuta este script.
    - Acción: "pythonw -m agente_impresion" (sin ventana) con la carpeta
      tools\ como directorio de trabajo (se calcula a partir de la
      ubicación de este script, no hay rutas fijas). Si no hay pythonw.exe,
      python.exe lanzado oculto desde powershell.exe. El agente escribe su
      propio log en %LOCALAPPDATA%\FoodOpsAgente\agente.log.
    - Reintenta cada 1 minuto hasta 999 veces si falla, sigue corriendo con
      batería y no tiene límite de tiempo de ejecución.
    - NO pide ni guarda el token. El agente lee su configuración de las
      variables de entorno del usuario; este script solo comprueba que las
      obligatorias existan y muestra su NOMBRE, nunca su valor.

    Las variables se configuran antes, una sola vez, por ejemplo con
    "Editar las variables de entorno de su cuenta" en Windows. No pegue el
    token en este script, en archivos compartidos ni en el repositorio.

.PARAMETER PythonExe
    Ruta a python.exe. Si se omite, se usa el "python" del PATH.

.PARAMETER Desinstalar
    Borra la tarea programada y termina.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\instalar_tarea.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\instalar_tarea.ps1 -PythonExe "C:\Python312\python.exe"

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\instalar_tarea.ps1 -Desinstalar

.NOTES
    NO PROBADO EN WINDOWS: escrito y revisado a mano. Pruébelo primero en la
    PC de la tienda siguiendo docs/RUNBOOK_ACTIVAR_CENTRO.md.
#>
[CmdletBinding()]
param(
    [string]$PythonExe,
    [switch]$Desinstalar
)

# Cualquier error no controlado detiene el script en vez de seguir a medias.
$ErrorActionPreference = 'Stop'

$NombreTarea = 'FoodOpsAgenteImpresion'

# Variables que el agente exige (ver Config.desde_entorno en agente.py).
$VariablesObligatorias = @(
    'FOODOPS_API_URL',
    'FOODOPS_AGENTE_TOKEN',
    'FOODOPS_IMPRESORA_IP'
)

# ---------------------------------------------------------------------------
# 1. Desinstalar, si se pidió.
# ---------------------------------------------------------------------------
if ($Desinstalar) {
    $existente = Get-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue
    if ($existente) {
        # Detiene la instancia en curso (si hay) antes de borrar la tarea.
        Stop-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:$false
        Write-Host "Tarea '$NombreTarea' eliminada."
    } else {
        Write-Host "La tarea '$NombreTarea' no existe; no hay nada que eliminar."
    }
    exit 0
}

# ---------------------------------------------------------------------------
# 2. Ubicar la carpeta del agente a partir de este script.
#    Este archivo vive en tools\agente_impresion\; "python -m agente_impresion"
#    tiene que ejecutarse desde la carpeta PADRE (tools\) para que Python
#    encuentre el paquete agente_impresion.
# ---------------------------------------------------------------------------
$CarpetaAgente = $PSScriptRoot
$CarpetaTrabajo = Split-Path -Parent $CarpetaAgente
if (-not (Test-Path (Join-Path $CarpetaAgente '__main__.py'))) {
    throw "No se encontró __main__.py junto a este script ($CarpetaAgente). " +
          "Ejecute instalar_tarea.ps1 desde la carpeta agente_impresion."
}

# ---------------------------------------------------------------------------
# 3. Verificar las variables de entorno obligatorias.
#    La tarea arranca al iniciar sesión y hereda las variables de USUARIO o
#    de SISTEMA (no las de esta ventana de PowerShell), por eso se revisan
#    esos dos ámbitos. Solo se muestra el nombre, nunca el valor.
# ---------------------------------------------------------------------------
$faltan = @()
foreach ($nombre in $VariablesObligatorias) {
    $enUsuario = [Environment]::GetEnvironmentVariable($nombre, 'User')
    $enSistema = [Environment]::GetEnvironmentVariable($nombre, 'Machine')
    if ([string]::IsNullOrWhiteSpace($enUsuario) -and [string]::IsNullOrWhiteSpace($enSistema)) {
        $faltan += $nombre
    } else {
        Write-Host "  OK  $nombre (definida)"
    }
}
if ($faltan.Count -gt 0) {
    Write-Host ''
    Write-Host 'Faltan variables de entorno obligatorias del agente:' -ForegroundColor Red
    foreach ($nombre in $faltan) { Write-Host "  - $nombre" -ForegroundColor Red }
    Write-Host ''
    Write-Host 'Defínalas como variables de entorno de su cuenta de usuario y vuelva a ejecutar este script.'
    Write-Host 'No se creó ni modificó ninguna tarea.'
    exit 1
}

# ---------------------------------------------------------------------------
# 4. Resolver python.exe y comprobar que sea Python 3.10 o superior.
#    Evita el "python" falso de la Microsoft Store (alias que abre la tienda
#    en vez de ejecutar Python): si no responde con una versión válida, se
#    detiene.
# ---------------------------------------------------------------------------
if ($PythonExe) {
    if (-not (Test-Path $PythonExe)) { throw "No existe el Python indicado: $PythonExe" }
    $Python = (Resolve-Path $PythonExe).Path
} else {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "No se encontró 'python' en el PATH. Instale Python 3.10+ o use -PythonExe <ruta>."
    }
    $Python = $cmd.Source
}

# try/catch: en PowerShell 5.1, con ErrorActionPreference = Stop, cualquier
# texto en stderr de un ejecutable (p. ej. el alias de la Store) se vuelve
# un error que cortaría el script sin el mensaje claro de abajo.
try {
    $version = (& $Python --version 2>&1 | Out-String).Trim()
} catch {
    $version = $_.ToString()
}
if ($version -notmatch '^Python (\d+)\.(\d+)') {
    throw "'$Python' no respondió como Python (salida: '$version'). Use -PythonExe con la ruta real de python.exe."
}
if ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 10)) {
    throw "Se requiere Python 3.10 o superior; '$Python' es $version."
}
Write-Host "  OK  $version ($Python)"

# ---------------------------------------------------------------------------
# 5. Log del agente. Lo escribe el PROPIO agente (configurar_log en
#    agente.py), no una redirección de cmd.exe: cmd.exe abriría una ventana
#    de consola visible. Ruta: FOODOPS_ARCHIVO_LOG si el usuario la definió;
#    si no, %LOCALAPPDATA%\FoodOpsAgente\agente.log (rotativo, 5 x 5 MB).
# ---------------------------------------------------------------------------
$ArchivoLog = [Environment]::GetEnvironmentVariable('FOODOPS_ARCHIVO_LOG', 'User')
if ([string]::IsNullOrWhiteSpace($ArchivoLog)) {
    $ArchivoLog = [Environment]::GetEnvironmentVariable('FOODOPS_ARCHIVO_LOG', 'Machine')
}
if ([string]::IsNullOrWhiteSpace($ArchivoLog)) {
    $ArchivoLog = Join-Path (Join-Path $env:LOCALAPPDATA 'FoodOpsAgente') 'agente.log'
}
New-Item -ItemType Directory -Path (Split-Path -Parent $ArchivoLog) -Force | Out-Null

# ---------------------------------------------------------------------------
# 6. Acción, SIN ventana visible:
#    a) Si existe pythonw.exe junto al intérprete (lo normal en una
#       instalación de python.org): se ejecuta directo. pythonw no abre
#       consola y, al no tener consola, el agente escribe su log solo.
#    b) Si no existe: python.exe lanzado desde powershell.exe con
#       -WindowStyle Hidden (las tareas programadas no tienen opción de
#       ventana oculta propia). Puede verse un parpadeo breve al iniciar
#       sesión. Como python.exe sí tiene consola (oculta), se le indica el
#       log con FOODOPS_ARCHIVO_LOG, salvo que el usuario ya la tenga.
# ---------------------------------------------------------------------------
$Pythonw = Join-Path (Split-Path -Parent $Python) 'pythonw.exe'
if (Test-Path $Pythonw) {
    $accion = New-ScheduledTaskAction -Execute $Pythonw -Argument '-m agente_impresion' `
        -WorkingDirectory $CarpetaTrabajo
    $modo = "pythonw.exe ($Pythonw)"
} else {
    # Comillas simples de PowerShell dentro del comando: se duplican si la
    # ruta trae un apóstrofo.
    $pyEsc = $Python.Replace("'", "''")
    $logEsc = $ArchivoLog.Replace("'", "''")
    $comando = 'if (-not $env:FOODOPS_ARCHIVO_LOG) {{ $env:FOODOPS_ARCHIVO_LOG = ''{1}'' }}; & ''{0}'' -m agente_impresion' -f $pyEsc, $logEsc
    $argumentos = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -Command "{0}"' -f $comando
    $accion = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argumentos `
        -WorkingDirectory $CarpetaTrabajo
    $modo = "python.exe oculto vía powershell.exe ($Python); no se encontró pythonw.exe"
}

# ---------------------------------------------------------------------------
# 7. Desencadenador: al iniciar sesión el usuario actual.
# ---------------------------------------------------------------------------
$usuario = "$env:USERDOMAIN\$env:USERNAME"
$desencadenador = New-ScheduledTaskTrigger -AtLogOn -User $usuario

# ---------------------------------------------------------------------------
# 8. Configuración:
#    - RestartCount/RestartInterval: si la tarea falla, reintentar cada 1 min
#      hasta 999 veces.
#    - AllowStartIfOnBatteries / DontStopIfGoingOnBatteries: no detenerse al
#      pasar a batería.
#    - ExecutionTimeLimit 0: sin límite (el valor por defecto de Windows,
#      72 h, mataría al agente a los 3 días).
#    - MultipleInstances IgnoreNew: nunca dos agentes a la vez.
#    - StartWhenAvailable: si se perdió el arranque, correrlo en cuanto se pueda.
#    - No se usa RunOnlyIfNetworkAvailable: un cambio o corte de red no
#      detiene la tarea; el propio agente reintenta la conexión al backend.
# ---------------------------------------------------------------------------
$configuracion = New-ScheduledTaskSettingsSet `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

# ---------------------------------------------------------------------------
# 9. Principal: el usuario actual, sesión interactiva, sin privilegios de
#    administrador (el agente no los necesita). Así la tarea hereda las
#    variables de entorno de esta cuenta.
# ---------------------------------------------------------------------------
$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited

# ---------------------------------------------------------------------------
# 10. Registrar (o reemplazar con -Force) la tarea.
# ---------------------------------------------------------------------------
Register-ScheduledTask `
    -TaskName $NombreTarea `
    -Description 'Agente de impresión de FoodOps: imprime tickets y abre el cajón de la tienda.' `
    -Action $accion `
    -Trigger $desencadenador `
    -Settings $configuracion `
    -Principal $principal `
    -Force | Out-Null

Write-Host ''
Write-Host "Tarea '$NombreTarea' instalada para $usuario." -ForegroundColor Green
Write-Host "  Ejecución:             $modo"
Write-Host "  Directorio de trabajo: $CarpetaTrabajo"
Write-Host "  Log:                   $ArchivoLog"
Write-Host ''
Write-Host 'Arrancará sola en el próximo inicio de sesión. Para arrancarla ahora:'
Write-Host "  Start-ScheduledTask -TaskName $NombreTarea"
Write-Host 'El agente corre SIN ventana. Para saber qué hace, revise el log:'
Write-Host "  Get-Content -Wait -Tail 20 '$ArchivoLog'"
Write-Host 'Estado de la tarea:'
Write-Host "  Get-ScheduledTask -TaskName $NombreTarea | Get-ScheduledTaskInfo"
Write-Host 'Detener el agente:'
Write-Host "  Stop-ScheduledTask -TaskName $NombreTarea"
