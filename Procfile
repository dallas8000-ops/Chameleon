# Chameleon runs as one Railway service because Railway volumes are one-to-one with
# services: the API, the Celery worker and Celery Beat all need the same private
# media volume, so they share a container. Splitting them out requires shared
# object storage (P1), not a second volume.
#
# `honcho start` exits when any child exits, including a clean exit, which is why
# railway.json sets restartPolicyType=ALWAYS: Railway restarts the whole service
# if gunicorn, the worker or beat dies.
web: cd backend && /opt/venv/bin/gunicorn chameleon.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3} --timeout 120 --access-logfile - --error-logfile -
worker: cd backend && /opt/venv/bin/celery -A chameleon worker --loglevel ${CELERY_LOG_LEVEL:-info} --concurrency ${CELERY_CONCURRENCY:-2}
beat: cd backend && /opt/venv/bin/celery -A chameleon beat --loglevel ${CELERY_LOG_LEVEL:-info} --schedule ${CELERY_BEAT_SCHEDULE_FILE:-/data/celerybeat-schedule}
