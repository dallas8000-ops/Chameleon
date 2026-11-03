"""Prints whether PyTorch can use the graphics card. Exits 1 if it cannot (run-gpu.ps1 uses this)."""
import sys

try:
    import torch
except ImportError as error:
    print(f"PyTorch is not installed correctly: {error}")
    sys.exit(1)

print("PyTorch", torch.__version__, "| CUDA build", torch.version.cuda)
if not torch.cuda.is_available():
    print("CUDA available: False (PyTorch cannot see an NVIDIA card)")
    sys.exit(1)
props = torch.cuda.get_device_properties(0)
print(f"CUDA available: True | {props.name} | {props.total_memory / 1024**3:.1f} GB")
