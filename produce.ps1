# Produces an episode end to end (pictures, voice lines, MP4) without the browser. Usage:
#   .\produce.ps1 -Project "Ep 1"            # plan only: lists scenes, words and expected length
#   .\produce.ps1 -Project "Ep 1" -Run       # make everything and save the MP4 in local-fixtures\exports
# The GPU worker (run-gpu.ps1) must be running for -Run.
#   .\produce.ps1 -Project "Ep 1" -Narrator "Marcus Johnson" -Run   # narration lines spoken in Marcus's voice
#   .\produce.ps1 -Project "Ep 1" -Show      # print the full script and characters
#   .\produce.ps1 -Project "Ep 1" -Run -RedoPictures   # remake every picture, keep the voices
param([string]$Project = 'Ep 1', [string]$Narrator = '', [switch]$Run, [switch]$Show, [switch]$RedoPictures)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

. "$root\local-env.ps1"
Push-Location "$root\backend"
$env:PYTHONPATH = "$root\backend"
$env:PRODUCE_PROJECT = $Project
$env:PRODUCE_NARRATOR = $Narrator
$env:PRODUCE_REDO_PICTURES = $(if ($RedoPictures) { '1' } else { '' })
$env:PRODUCE_MODE = $(if ($Run) { 'run' } elseif ($Show) { 'show' } else { 'plan' })
# Back to the folder you ran this from, even if it fails.
try { & $python "$root\produce.py" } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'produce failed' }
