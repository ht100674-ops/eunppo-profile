# Optional developer validation. Normal users only launch StreamShortStudio.exe.
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Exe = Join-Path $Root 'StreamShortStudio.exe'
if (-not (Test-Path $Exe)) { throw 'Run this script inside the generated Portable folder, next to StreamShortStudio.exe.' }
$Sandbox = Join-Path $env:SystemRoot 'System32\WindowsSandbox.exe'
if (-not (Test-Path $Sandbox)) { throw 'Windows Sandbox must already be enabled on a supported edition. This test was not run automatically.' }
$Results = Join-Path $Root 'SandboxResults'
New-Item -ItemType Directory -Force $Results | Out-Null
$EscapedRoot = [System.Security.SecurityElement]::Escape($Root)
$EscapedResults = [System.Security.SecurityElement]::Escape($Results)
$Config = Join-Path $Results 'offline-test.wsb'
@"
<Configuration>
  <Networking>Disable</Networking>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <MappedFolders>
    <MappedFolder><HostFolder>$EscapedRoot</HostFolder><SandboxFolder>C:\StreamShort</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>$EscapedResults</HostFolder><SandboxFolder>C:\Results</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>
  </MappedFolders>
  <LogonCommand><Command>cmd.exe /c C:\StreamShort\StreamShortStudio.exe --self-test C:\Results\clean-windows-self-test.json --require-frozen</Command></LogonCommand>
</Configuration>
"@ | Set-Content -Encoding UTF8 $Config
Start-Process -FilePath $Sandbox -ArgumentList ('"' + $Config + '"')
Write-Host 'Network-disabled Windows Sandbox started. Results are written to SandboxResults\clean-windows-self-test.json.'
Write-Host 'A status of passed is required. No result file means unverified, not passed.'
