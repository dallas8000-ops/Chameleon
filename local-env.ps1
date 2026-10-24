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
