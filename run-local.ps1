# Starts Chameleon locally (API via run-api.ps1, plus the Vite frontend) and opens the browser.
# Installs backend and frontend dependencies on the way, so this is the only command you need.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
. "$root\local-env.ps1"

# The website window loads local-env.ps1 too, so its /api proxy points at the same backend port.
$web = ". '$root\local-env.ps1'; Set-Location '$root\frontend'; npm install --no-audit --no-fund; npm run dev -- --host 127.0.0.1"

Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', "`"$root\run-api.ps1`""
Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $web
# With an NVIDIA card, also start the local GPU worker (set CHAMELEON_NO_GPU=1 to skip it).
if (-not $env:CHAMELEON_NO_GPU -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', "`"$root\run-gpu.ps1`""
}

# Open the browser once the API answers (first run can take a minute while pip installs).
for ($i = 0; $i -lt 90; $i++) {
    try { Invoke-WebRequest "$($env:BACKEND_URL)/api/health/" -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 2 }
}
Start-Process 'http://127.0.0.1:5173'
