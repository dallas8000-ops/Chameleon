# Lists characters in the local database, and optionally gives one a voice sample. Usage:
#   .\set-voice.ps1                                         # list characters
#   .\set-voice.ps1 -Character "Ray" -File C:\path\to\voice.wav
param([string]$Character, [string]$File = "$PSScriptRoot\local-fixtures\voice\reference.wav")
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

. "$root\local-env.ps1"
Push-Location "$root\backend"
$env:PYTHONPATH = "$root\backend"
$env:VOICE_CHARACTER = $Character
$env:VOICE_FILE = $File
try {
    & $python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'migrate failed' }
    & $python "$root\set-voice.py"
} finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'set-voice failed' }
