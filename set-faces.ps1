# Attaches the photos in local-fixtures\characters as each character's face reference.
#   .\set-faces.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

. "$root\local-env.ps1"
Push-Location "$root\backend"
$env:PYTHONPATH = "$root\backend"
try { & $python "$root\set-faces.py" } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'set-faces failed' }
