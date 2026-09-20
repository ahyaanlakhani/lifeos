<#
.SYNOPSIS
  Run the whole system in demo mode: no VM, no NemoClaw, no credentials.

.DESCRIPTION
  The PowerShell equivalent of scripts/demo.sh. Starts the agent host on :8000
  in the background and Glass Box on :3000 in the foreground; Ctrl-C stops
  both.

  Note it calls npm.cmd rather than npm. On Windows `npm` is a PowerShell
  script, and the default execution policy blocks it with an
  UnauthorizedAccess error. npm.cmd is a batch file and is not subject to
  that policy, so this works without changing any security setting.

.EXAMPLE
  .\scripts\demo.ps1

.EXAMPLE
  .\scripts\demo.ps1 -NoLoop      # play the scripted session once, then stop
#>
[CmdletBinding()]
param(
    [switch]$NoLoop
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:DEMO = "true"
if ($NoLoop) { $env:DEMO_LOOP = "0" } else { $env:DEMO_LOOP = "1" }

$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) { throw "python is not on PATH. Python 3.11+ is required." }

$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
if (-not $npm) { throw "npm.cmd is not on PATH. Node 20+ is required." }

if (-not (Test-Path "apps/glassbox/node_modules")) {
    Write-Host "Installing Glass Box dependencies..." -ForegroundColor Cyan
    & npm.cmd install --prefix apps/glassbox --no-audit --no-fund
}

Write-Host "Starting the agent host on http://localhost:8000 ..." -ForegroundColor Cyan
$host_proc = Start-Process -FilePath $python.Source `
    -ArgumentList "-m", "apps.host" `
    -WorkingDirectory $root `
    -PassThru -WindowStyle Hidden

try {
    Write-Host "Starting Glass Box on http://localhost:3000 ..." -ForegroundColor Cyan
    Write-Host "First start takes ~30s while Next compiles. Ctrl-C stops both." -ForegroundColor DarkGray
    & npm.cmd run dev --prefix apps/glassbox
}
finally {
    if ($host_proc -and -not $host_proc.HasExited) {
        Write-Host "`nStopping the agent host..." -ForegroundColor DarkGray
        Stop-Process -Id $host_proc.Id -Force -ErrorAction SilentlyContinue
    }
}
