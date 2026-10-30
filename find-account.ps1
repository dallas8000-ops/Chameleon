# Lists every account in the local database with its workspaces and projects, then optionally
# sets one account's password and confirms it works. Usage:
#   .\find-account.ps1                         # list accounts and projects
#   .\find-account.ps1 -Email you@example.com  # list, then prompt for a new password for that account
param([string]$Email)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

. "$root\local-env.ps1"
Set-Location "$root\backend"
& $python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'migrate failed' }

if ($Email) {
    $secure = Read-Host "New password for $Email" -AsSecureString
    $env:RESET_EMAIL = $Email
    $env:RESET_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}

$env:PYTHONPATH = "$root\backend"
try {
    & $python "$root\find-account.py"
    if ($LASTEXITCODE -ne 0) { throw 'find-account failed' }
} finally {
    Remove-Item Env:RESET_PASSWORD -ErrorAction SilentlyContinue
}
