# Starts the local GPU worker so generation runs on this computer's NVIDIA card (RTX 50-series or older).
# Uses its own virtualenv (.venv-gpu) because PyTorch with CUDA is large. The first run installs PyTorch for
# CUDA 12.8 and downloads the picture model (about 7 GB), so it takes a while.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
# Not named $python: local-env.ps1 sets $python to the backend virtualenv, which has no PyTorch.
$gpuPython = "$root\.venv-gpu\Scripts\python.exe"

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { throw 'nvidia-smi was not found. Install the NVIDIA driver first.' }
if (-not (Test-Path $gpuPython)) {
    Write-Host 'Creating the GPU virtualenv...'
    py -3.11 -m venv "$root\.venv-gpu"
}
Write-Host 'Updating pip (newer pip resumes interrupted downloads)...'
& $gpuPython -m pip install --disable-pip-version-check --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
Write-Host 'Installing PyTorch for CUDA 12.8 (about 2.75 GB)...'
# Only from the CUDA index: the PyPI build of torch for Windows is CPU-only. The download is large, so a
# dropped connection resumes instead of leaving a partial file that fails pip's checksum check.
& $gpuPython -m pip install --disable-pip-version-check --no-cache-dir --resume-retries 20 torch --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'PyTorch install failed' }
Write-Host 'Installing the picture model libraries...'
& $gpuPython -m pip install --disable-pip-version-check -r "$root\worker\requirements-local.txt"
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

. "$root\local-env.ps1"
Set-Location "$root\worker"
& $gpuPython "$root\worker\check_gpu.py"
if ($LASTEXITCODE -ne 0) { throw 'PyTorch cannot see the graphics card.' }
Write-Host 'Making sure the picture model is downloaded (about 7 GB the first time)...'
& $gpuPython -m chameleon_worker.text_to_image --download
if ($LASTEXITCODE -ne 0) { throw 'Model download failed' }
& $gpuPython -m chameleon_worker.local_server
