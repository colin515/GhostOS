$ErrorActionPreference = 'Stop'
$target = Join-Path $env:RUNNER_TEMP 'GhostOS Upgrade Smoke'
$oldSetup = Join-Path $env:RUNNER_TEMP 'GhostOS_Installer_v1.2.2.exe'
$newSetup = (Get-Item "dist/GhostOS_Installer_v$env:APP_VERSION.exe").FullName
$dataRoot = Join-Path $env:LOCALAPPDATA 'GhostOS'

function Install-Setup([string]$File, [string[]]$Extra = @()) {
    $arguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/FORCECLOSEAPPLICATIONS') + $Extra
    $process = Start-Process $File -ArgumentList $arguments -PassThru
    if (-not $process.WaitForExit(180000)) { throw 'Installer timed out' }
    if ($process.ExitCode -ne 0) { throw "Installer exit $($process.ExitCode)" }
}

Invoke-WebRequest 'https://github.com/colin515/GhostOS/releases/download/v1.2.2/GhostOS_Installer_v1.2.2.exe' -OutFile $oldSetup
$oldHash = (Get-FileHash $oldSetup -Algorithm SHA256).Hash.ToLower()
if ($oldHash -ne 'dca2c51a25645ec821af54538046a5d819b27416a7247ec6a4a05d070b9e456b') { throw 'Previous installer hash mismatch' }
Install-Setup $oldSetup @('/DIR="' + $target + '"')

New-Item -ItemType Directory -Force $dataRoot | Out-Null
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = $listener.LocalEndpoint.Port
$listener.Stop()
@{tier=1; model='llava:7b'; setup_complete=$true; web_port=$port} | ConvertTo-Json | Set-Content (Join-Path $dataRoot 'settings.json') -Encoding utf8
foreach ($folder in @('recipes','logs','voice-model')) {
    $directory = Join-Path $dataRoot $folder
    New-Item -ItemType Directory -Force $directory | Out-Null
    Set-Content (Join-Path $directory 'upgrade-preserve.txt') "preserve $folder"
}

# Old GhostOS runs without a visible window, reproducing a blocked background instance.
$old = Start-Process (Join-Path $target 'GhostOS.exe') -ArgumentList '--web' -PassThru
$ready = $false
for ($i=0; $i -lt 60; $i++) {
    if ($old.HasExited) { throw 'Previous GhostOS failed to start' }
    $client = [System.Net.Sockets.TcpClient]::new()
    try { $client.Connect('127.0.0.1', $port); $ready = $true; break } catch { Start-Sleep -Milliseconds 250 } finally { $client.Dispose() }
}
if (-not $ready) { throw 'Previous headless runtime did not become ready' }

# No /DIR: the unchanged AppId must select the previous custom install folder.
Install-Setup $newSetup
if (-not $old.WaitForExit(15000)) { throw 'Upgrade did not close the old background GhostOS' }
$version = & (Join-Path $target 'GhostOS.exe') --version
if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne $env:APP_VERSION) { throw 'Previous install folder was not upgraded' }
$configPath = Join-Path $dataRoot 'settings.json'
$config = Get-Content $configPath -Raw | ConvertFrom-Json
if ($config.model -ne 'llava:7b') { throw 'Upgrade changed valid saved model settings' }
& (Join-Path $target 'GhostOS.exe') --desktop-smoke-test
if ($LASTEXITCODE -ne 0) { throw 'Upgraded desktop failed to open' }

# The old app could not start with malformed settings: the new app must recover and show UI.
Set-Content $configPath '{broken settings'
& (Join-Path $target 'GhostOS.exe') --desktop-smoke-test
if ($LASTEXITCODE -ne 0) { throw 'Desktop did not recover from broken settings' }
$config = Get-Content $configPath -Raw | ConvertFrom-Json
if ($config.tier -ne 1) { throw 'Recovered settings must default to Strict permissions' }
if (-not (Get-ChildItem $dataRoot -Filter 'settings.backup_*.json')) { throw 'Original settings were not backed up' }

# Re-run the same installer in repair mode, without relying on the existing app opening.
Install-Setup $newSetup @('/TASKS="repairsettings"')
foreach ($folder in @('recipes','logs','voice-model')) {
    $marker = Join-Path (Join-Path $dataRoot $folder) 'upgrade-preserve.txt'
    if ((Get-Content $marker -Raw).Trim() -ne "preserve $folder") { throw "Lost $folder during update/repair" }
}
$entries = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' | Where-Object { $_.DisplayName -eq 'GhostOS' }
if (@($entries).Count -ne 1) { throw 'Update created duplicate Installed apps entries' }
$uninstall = Start-Process (Join-Path $target 'unins000.exe') -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -Wait -PassThru
if ($uninstall.ExitCode -ne 0) { throw 'Uninstall after upgrade failed' }
if (-not (Test-Path (Join-Path $dataRoot 'voice-model/upgrade-preserve.txt'))) { throw 'Uninstall removed user model data' }
Write-Output 'Verified upgrade from 1.2.2, previous folder reuse, hidden-process shutdown, desktop startup, corrupt-settings recovery, repair and preserved user data'
