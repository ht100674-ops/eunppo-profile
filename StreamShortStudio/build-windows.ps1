# Developer / CI script. End users never execute this file.
param([string]$Python = 'python', [switch]$SkipFetch)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Invoke-Python {
    & $Python @args
    if ($LASTEXITCODE -ne 0) { throw "Python step failed: $($args -join ' ')" }
}
Invoke-Python -m pip install -r requirements-dev.txt
if (-not $SkipFetch) { Invoke-Python tools/fetch_ffmpeg.py }
Invoke-Python tools/doctor.py
Invoke-Python -m pytest -q --junitxml=artifacts/unit-tests.xml
Invoke-Python -m PyInstaller --noconfirm --clean StreamShortStudio.spec
Invoke-Python tools/package_portable.py

# Run the actual EXE away from source, with no Python/pip/FFmpeg on PATH.
$Exe = Join-Path $PSScriptRoot 'dist\StreamShortStudio\StreamShortStudio.exe'
$ReportDir = Join-Path $env:TEMP ('StreamShort-isolated-' + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Force $ReportDir | Out-Null
$Report = Join-Path $ReportDir 'self-test.json'
$SavedPath = $env:PATH
$SavedPythonPath = $env:PYTHONPATH
$SavedPythonHome = $env:PYTHONHOME
$SavedQtPluginPath = $env:QT_PLUGIN_PATH
$SavedQtPlatform = $env:QT_QPA_PLATFORM
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    Remove-Item Env:QT_PLUGIN_PATH -ErrorAction SilentlyContinue
    $env:QT_QPA_PLATFORM = 'offscreen'
    $Process = Start-Process -FilePath $Exe -ArgumentList @('--self-test', ('"' + $Report + '"'), '--require-frozen') -WorkingDirectory $ReportDir -PassThru
    if (-not $Process.WaitForExit(240000)) { Stop-Process -Id $Process.Id -Force; throw 'Frozen EXE self-test timed out.' }
    $Process.Refresh()
    if ($Process.ExitCode -ne 0) {
        if (Test-Path $Report) { Get-Content $Report }
        throw "Frozen EXE self-test failed: $($Process.ExitCode)"
    }
    if (-not (Test-Path $Report)) { throw 'Frozen EXE did not create a test report.' }
} finally {
    $env:PATH = $SavedPath
    $env:PYTHONPATH = $SavedPythonPath
    $env:PYTHONHOME = $SavedPythonHome
    $env:QT_PLUGIN_PATH = $SavedQtPluginPath
    $env:QT_QPA_PLATFORM = $SavedQtPlatform
    if (Test-Path $Report) { Copy-Item $Report '.\artifacts\self-test.json' -Force }
}
Invoke-Python tools/finalize_portable.py $Report
Write-Host 'Portable ZIP created: artifacts\StreamShortStudio-Windows-x64-Portable.zip'
