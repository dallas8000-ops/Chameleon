# Single Railway service image: the API, Celery worker and Celery Beat share one
# container (see Procfile) because a Railway volume attaches to only one service
# and all three need the same private media directory.
#
# A root Dockerfile is used by Railway whichever default builder is selected, so
# builds and redeploys no longer depend on railway.json choosing Nixpacks.

FROM node:20-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
# Vite, React and TypeScript are devDependencies, so install them explicitly.
RUN npm ci --include=dev
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# FFmpeg provides ffmpeg and ffprobe for export assembly. Text overlays are drawn
# with libass, which needs fontconfig and at least one font.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fontconfig fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY Procfile railway.json ./
COPY --from=frontend /app/frontend/dist frontend/dist
# STATIC_ROOT is image content. The placeholder values only satisfy settings
# import; they never reach a running service.
RUN cd backend \
    && SECRET_KEY=collectstatic-build-only-placeholder-value-not-used-at-runtime \
       DATABASE_URL=sqlite:///collectstatic.sqlite3 \
       REDIS_URL=redis://127.0.0.1:6379/0 \
       /opt/venv/bin/python manage.py collectstatic --noinput

# Verifies configuration with the volume mounted, migrates, then supervises
# gunicorn, the Celery worker and Celery Beat. Keep in sync with railway.json.
CMD ["sh", "-c", "/opt/venv/bin/python backend/manage.py check_deployment --role all && /opt/venv/bin/python backend/manage.py migrate --noinput && /opt/venv/bin/honcho start -f Procfile"]
