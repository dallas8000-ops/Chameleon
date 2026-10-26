# Starts the local GPU worker so generation runs on this computer's NVIDIA card (RTX 50-series or older).
# Uses its own virtualenv (.venv-gpu) because PyTorch with CUDA is large. The first run installs PyTorch for
# CUDA 12.8 and downloads the picture model (about 7 GB), so it takes a while.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "$root\.venv-gpu\Scripts\python.exe"

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { throw 'nvidia-smi was not found. Install the NVIDIA driver first.' }
if (-not (Test-Path $python)) {
    Write-Host 'Creating the GPU virtualenv...'
    py -3.11 -m venv "$root\.venv-gpu"
}
Write-Host 'Installing GPU worker dependencies (PyTorch for CUDA 12.8, diffusers)...'
& $python -m pip install --disable-pip-version-check -r "$root\worker\requirements-local.txt"
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

. "$root\local-env.ps1"
Set-Location "$root\worker"
& $python -c "import torch,sys; ok=torch.cuda.is_available(); print('CUDA available:', ok, '|', torch.cuda.get_device_name(0) if ok else 'no GPU'); sys.exit(0 if ok else 1)"
if ($LASTEXITCODE -ne 0) { throw 'PyTorch cannot see the graphics card.' }
Write-Host 'Making sure the picture model is downloaded...'
& $python -m chameleon_worker.text_to_image --download
if ($LASTEXITCODE -ne 0) { throw 'Model download failed' }
& $python -m chameleon_worker.local_server
