# Replaces an episode's scenes with its longer script.
#   .\load-episode.ps1 -File content\muzungu\ep01.json
param([Parameter(Mandatory)][string]$File)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

$env:EPISODE_FILE = (Resolve-Path $File).Path
. "$root\local-env.ps1"
Push-Location "$root\backend"
$env:PYTHONPATH = "$root\backend"
try { & $python "$root\load-episode.py" } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'load-episode failed' }
