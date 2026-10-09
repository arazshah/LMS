# --- Stage 1: build CSS and copy self-hosted frontend assets ---
FROM node:22-alpine AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY scripts ./scripts
COPY frontend ./frontend
COPY templates ./templates
COPY apps ./apps
RUN npm run build

# --- Stage 2: Django app ---
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
       libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:app . .
COPY --from=frontend --chown=app:app /app/static/dist ./static/dist

RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && mkdir -p /app/media /app/data && chown app:app /app/media /app/data

USER app
EXPOSE 80
ENTRYPOINT ["./docker/entrypoint.sh"]
CMD ["web"]
