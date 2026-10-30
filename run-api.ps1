# Starts the Django API locally without Postgres/Redis: SQLite, in-memory cache, inline Celery.
# Creates/updates the virtualenv first so new backend dependencies are always installed.
# Data lives in .local-data (see local-env.ps1).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "$root\.venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host 'Creating virtualenv...'
    py -3.11 -m venv "$root\.venv"
}
Write-Host 'Installing backend dependencies...'
& $python -m pip install --quiet --disable-pip-version-check -r "$root\backend\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

. "$root\local-env.ps1"
Set-Location "$root\backend"
& $python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'migrate failed' }
& $python manage.py runserver "127.0.0.1:$($env:CHAMELEON_API_PORT)"
