#!/bin/sh
set -e

case "$1" in
  web)
    python manage.py migrate --noinput
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-3}" \
      --timeout "${GUNICORN_TIMEOUT:-60}" \
      --access-logfile -
    ;;
  worker)
    exec celery -A config worker --loglevel=info --concurrency "${CELERY_CONCURRENCY:-2}"
    ;;
  *)
    exec "$@"
    ;;
esac
