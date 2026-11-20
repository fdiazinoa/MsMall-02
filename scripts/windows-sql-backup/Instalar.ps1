#requires -Version 5.1
param(
    [string]$Destino = 'C:\Respaldos\MsMall',
    [ValidatePattern('^([01][0-9]|2[0-3]):[0-5][0-9]$')][string]$Hora = '02:00',
    [switch]$SinSesionAbierta,
    [switch]$LoginOnly
)
$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
$config = Get-Content -LiteralPath (Join-Path $source 'config.json') -Raw | ConvertFrom-Json
$mall = [guid]::Parse($config.mall_id).ToString()
# One protected installation and task per Mall. No passwords in command line or files.
$install = Join-Path $env:LOCALAPPDATA "MsMall\SQLBackups\$mall"
if ($install.Contains('"') -or $Destino.Contains('"')) { throw 'La ruta no puede contener comillas.' }
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskName = "MsMall SQL $mall"
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and $existing.State -eq 'Running') { throw 'Espera a que termine el respaldo actual antes de configurar.' }
New-Item -ItemType Directory -Force -Path $install | Out-Null
& icacls.exe $install /inheritance:r /grant:r "${identity}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'No se pudo proteger la carpeta de sesión.' }
foreach ($name in @('backup_client.py','config.json')) {
    $from = Join-Path $source $name
    $to = Join-Path $install $name
    if ([IO.Path]::GetFullPath($from) -ne [IO.Path]::GetFullPath($to)) { Copy-Item -LiteralPath $from -Destination $to -Force }
}
# Requires an installed official Python 3.11+; never installs software silently.
$python = (& py.exe -3 -c 'import sys; assert sys.version_info >= (3,11); print(sys.executable)')
if ($LASTEXITCODE -ne 0 -or -not $python) { throw 'Instala Python 3.11 o superior desde python.org (incluido Python Launcher) y vuelve a ejecutar.' }
$python = $python.Trim()
$client = Join-Path $install 'backup_client.py'
$configPath = Join-Path $install 'config.json'
& $python $client --config $configPath --destination $Destino --login
if ($LASTEXITCODE -ne 0) { throw 'No se pudo validar el inicio de sesión de MsMall.' }
if ($LoginOnly) { Write-Host 'Sesión renovada. La programación existente se conserva.'; exit 0 }
New-Item -ItemType Directory -Force -Path (Join-Path $Destino $mall) | Out-Null
# Protect local SQLs too. The client stores ZIPs, hashes and its execution lock here.
& icacls.exe (Join-Path $Destino $mall) /inheritance:r /grant:r "${identity}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'No se pudo proteger la carpeta de respaldos.' }
$action = New-ScheduledTaskAction -Execute $python -Argument "`"$client`" --config `"$configPath`" --destination `"$Destino`"" -WorkingDirectory $install
# The Windows clock defines Hora. Set the PC to Santo Domingo for the default 02:00.
$trigger = New-ScheduledTaskTrigger -Daily -At $Hora
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
if ($SinSesionAbierta) {
    $credential = Get-Credential -UserName $identity -Message 'Clave de Windows para ejecutar aunque cierres sesión (debe ser este mismo usuario).'
    if (-not $credential -or $credential.UserName -ne $identity) { throw 'Usa la misma cuenta Windows que inició sesión en MsMall.' }
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -User $identity -Password $credential.GetNetworkCredential().Password -RunLevel Limited -Force | Out-Null
    $credential = $null
} else {
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host 'Esta modalidad requiere mantener abierta la sesión Windows. Usa -SinSesionAbierta para ejecución desatendida.'
}
# Initial full is downloaded now; subsequent scheduled runs are daily differentials.
& $python $client --config $configPath --destination $Destino
if ($LASTEXITCODE -ne 0) { throw 'La tarea quedó registrada, pero el primer respaldo falló. Revisa disco, conexión, permisos o cuota y ejecuta la tarea de nuevo.' }
Write-Host "Configurado: $taskName. Carpeta: $Destino\$mall. Hora local de Windows: $Hora."
