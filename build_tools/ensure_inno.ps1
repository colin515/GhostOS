$ErrorActionPreference = 'Stop'
function Find-InnoCompiler {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    return $null
}
$compiler = Find-InnoCompiler
if (-not $compiler) {
    choco install innosetup --yes --no-progress
    if ($LASTEXITCODE -notin @(0, 3010)) { throw 'Inno Setup installation failed' }
    $compiler = Find-InnoCompiler
}
if (-not $compiler) { throw 'ISCC.exe was not found' }
$version = (Get-Item $compiler).VersionInfo.ProductVersion
Write-Host "Using Inno Setup $version at $compiler"
if ($env:GITHUB_ENV) { "GHOSTOS_ISCC=$compiler" >> $env:GITHUB_ENV }
if (Test-Path dist/build-dependencies.txt) {
    "`n# Inno Setup $version" | Add-Content dist/build-dependencies.txt
}
