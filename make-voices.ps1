# Gives the other characters synthetic AI voices (Kokoro, Apache-2.0) and attaches them as their voice samples.
#   .\make-voices.ps1
# Run run-gpu.ps1 once first so .venv-voice exists. Marcus keeps the voice cloned from your own video.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$voicePython = "$root\.venv-voice\Scripts\python.exe"
$outDir = "$root\local-fixtures\voice\synthetic"

# Kokoro's dry run showed it keeps the CUDA torch, transformers and numpy already in place.
& $voicePython -m pip install kokoro==0.9.4 soundfile
if ($LASTEXITCODE -ne 0) { throw 'kokoro install failed' }
& $voicePython "$root\worker\make_voice_samples.py" $outDir
if ($LASTEXITCODE -ne 0) { throw 'making the voice samples failed' }

foreach ($name in 'Kato', 'Mama Grace', 'Nakato', 'Sarah', 'The boy') {
    & "$root\set-voice.ps1" -Character $name -File "$outDir\$name.wav"
}
