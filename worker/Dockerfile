# GPU worker for RunPod Serverless. Phase 2 ships the "diagnostic" capability only; Phase 3 adds the real
# models and will switch this base to a CUDA/PyTorch image (RunPod mounts the GPU driver at run time, so
# nvidia-smi works from this slim image).
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY chameleon_worker/ chameleon_worker/
COPY handler.py .

CMD ["python", "-u", "handler.py"]
