# Shared environment for the local scripts (dot-source it: . "$root\local-env.ps1").
# Data lives in .local-data, outside e2e/.runtime (which the e2e harness wipes). On first use, existing
# work in e2e/.runtime is copied over so nothing is lost.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "$root\.venv\Scripts\python.exe"
$dataDir = "$root\.local-data"

if (-not (Test-Path "$dataDir\chameleon.sqlite3") -and (Test-Path "$root\e2e\.runtime\e2e.sqlite3")) {
    Write-Host "Moving existing local data from e2e\.runtime to .local-data ..."
    New-Item -ItemType Directory -Force $dataDir | Out-Null
    Copy-Item "$root\e2e\.runtime\e2e.sqlite3" "$dataDir\chameleon.sqlite3"
    if (Test-Path "$root\e2e\.runtime\media") { Copy-Item -Recurse "$root\e2e\.runtime\media" "$dataDir\media" }
}

$env:CHAMELEON_LOCAL_DATA_DIR = $dataDir
$env:DJANGO_SETTINGS_MODULE = 'chameleon.settings_local'
$env:SECRET_KEY = 'local-dev-only-' + ('x' * 40)
$env:DEBUG = '1'
$env:CELERY_BROKER_URL = 'memory://'
$env:ALLOWED_HOSTS = '127.0.0.1,localhost'
$env:CSRF_TRUSTED_ORIGINS = 'http://127.0.0.1:5173,http://localhost:5173'
# Not 8000: another app on this computer already uses it. The Vite proxy reads BACKEND_URL.
if (-not $env:CHAMELEON_API_PORT) { $env:CHAMELEON_API_PORT = '8010' }
$env:BACKEND_URL = "http://127.0.0.1:$($env:CHAMELEON_API_PORT)"

# Export needs FFmpeg and FFprobe. Right after `winget install Gyan.FFmpeg` they may not be on PATH until
# Windows is signed in again, so look in winget's folders and point the backend at them directly.
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    $ffmpeg = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.DirectoryName 'ffprobe.exe') } | Select-Object -First 1
    if ($ffmpeg) {
        $env:FFMPEG_BINARY = $ffmpeg.FullName
        $env:FFPROBE_BINARY = Join-Path $ffmpeg.DirectoryName 'ffprobe.exe'
    } else {
        Write-Host 'FFmpeg was not found, so export will not work. Install it with: winget install --id Gyan.FFmpeg -e'
    }
}

# Local GPU worker (run-gpu.ps1). The backend talks to it with the RunPod client, so these reuse the
# RunPod settings. The shared token is generated once and kept in .local-data, never in the repo.
$tokenFile = "$dataDir\local-gpu-token.txt"
if (-not (Test-Path $tokenFile)) {
    New-Item -ItemType Directory -Force $dataDir | Out-Null
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    [System.BitConverter]::ToString($bytes).Replace('-', '').ToLower() | Set-Content -NoNewline $tokenFile
}
$env:LOCAL_GPU_TOKEN = (Get-Content $tokenFile -Raw).Trim()
$env:LOCAL_GPU_PORT = '8189'
$env:RUNPOD_API_KEY = $env:LOCAL_GPU_TOKEN
$env:RUNPOD_ENDPOINT_ID = 'local'
$env:RUNPOD_API_BASE = "http://127.0.0.1:$($env:LOCAL_GPU_PORT)/v2"
$env:GENERATION_PUBLIC_URL = $env:BACKEND_URL
$env:GENERATION_MAX_ACTIVE_JOBS = '1'
$env:WORKER_ALLOW_INSECURE_UPLOAD = '1'
