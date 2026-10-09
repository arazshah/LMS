#!/bin/sh
set -e

# Generate a persistent secret key on first start unless one is provided.
DATA_DIR="${DJANGO_DATA_DIR:-/app/data}"
if [ -z "$DJANGO_SECRET_KEY" ] && [ ! -s "$DATA_DIR/secret_key" ]; then
  mkdir -p "$DATA_DIR"
  python -c "import secrets; print(secrets.token_urlsafe(64))" > "$DATA_DIR/secret_key"
  chmod 600 "$DATA_DIR/secret_key"
fi

case "$1" in
  web)
    python manage.py migrate --noinput
    python manage.py ensure_admin
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:80 \
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
