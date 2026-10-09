# LMS — lms.araz.me

سیستم آموزش آنلاین اختصاصی برای دوره‌های هوش مصنوعی مکانی (GeoAI).
معماری و فازبندی: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## اجرای محلی

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
npm install && npm run build          # CSS، فونت و htmx
cp .env.example .env                  # و مقدار DJANGO_DEBUG=True بگذارید
python manage.py migrate
python manage.py createsuperuser      # شماره موبایل + رمز
python manage.py runserver
```

بدون `DATABASE_URL`، محیط محلی از SQLite استفاده می‌کند. برای تغییر استایل‌ها `npm run watch:css` را اجرا کنید.

تست و lint:

```bash
pytest
ruff check . && ruff format --check .
```

## دیپلوی روی Coolify

### شاخه‌ها

| شاخه | دامنه | کاربرد |
|---|---|---|
| `main` | `lms.araz.me` | production |
| `develop` | `staging.lms.araz.me` | تست قبل از انتشار |

### راه‌اندازی (یک بار برای هر محیط)

1. در DNS برای `lms` و `staging.lms` رکورد A به IP سرور بسازید.
2. در Coolify از مسیر **New Resource → Docker Compose** مخزن `arazshah/LMS` را انتخاب کنید و شاخه را تعیین کنید.
3. برای سرویس `web` دامنه را تنظیم کنید (مثلاً `https://lms.araz.me`) و پورت را **8000** بگذارید.
4. متغیرهای محیطی را تعریف کنید (نمونه در `.env.example`):
   - `DJANGO_SECRET_KEY`: یک رشته تصادفی طولانی، مثلاً با `openssl rand -base64 48`
   - `DJANGO_ALLOWED_HOSTS=lms.araz.me`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://lms.araz.me`
   - `DJANGO_ADMIN_URL`: مسیر غیرقابل‌حدس برای پنل ادمین، مثلاً `my-panel-x7/`
   - `POSTGRES_PASSWORD`: رمز قوی
5. Webhook گیت‌هاب را فعال کنید تا هر push خودکار دیپلوی شود.
6. بعد از اولین دیپلوی، در ترمینال سرویس `web` در Coolify ادمین را بسازید:
   ```bash
   python manage.py createsuperuser
   ```

### سرویس‌ها

| سرویس | کار |
|---|---|
| `web` | Django + gunicorn. migrationها هنگام بالا آمدن خودکار اجرا می‌شوند. health check روی `/health/` |
| `worker` | Celery: تبدیل ویدیو و ارسال پیامک |
| `db` | PostgreSQL 17 (volume: `postgres-data`) |
| `redis` | صف Celery |

فایل‌های آپلودی در volume `media` نگهداری می‌شوند.
