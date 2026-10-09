from datetime import timedelta
from urllib.parse import quote

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.throttle import MAX_FAILURES
from apps.catalog.models import Category, Course
from apps.shop import services
from apps.shop.models import DiscountCode, Order
from apps.shop.reports import build_report


@pytest.fixture
def course(db):
    return Course.objects.create(
        category=Category.objects.create(title="GeoAI"),
        title="دوره منتشرشده",
        summary="خلاصه برای سئو",
        price=1_000_000,
        is_published=True,
    )


def test_persian_404(client, db):
    response = client.get("/no-such-page/")
    assert response.status_code == 404
    assert "پیدا نشد" in response.content.decode()


def test_500_template_renders_without_context():
    from django.template.loader import render_to_string

    assert "مشکلی پیش آمد" in render_to_string("500.html")


def test_seo_meta_and_sitemap(client, course):
    Course.objects.create(category=course.category, title="پیش‌نویس", price=1)
    body = client.get(course.get_absolute_url()).content.decode()
    assert '<meta name="description" content="خلاصه برای سئو">' in body
    assert '<meta property="og:title" content="دوره منتشرشده">' in body
    assert 'rel="canonical"' in body

    sitemap = client.get("/sitemap.xml").content.decode()
    assert quote(course.slug) in sitemap
    assert quote("پیش‌نویس") not in sitemap

    robots = client.get("/robots.txt").content.decode()
    assert "Sitemap:" in robots and "Disallow: /orders/" in robots and "admin" not in robots


def test_mobile_menu_present(client, db):
    body = client.get("/").content.decode()
    assert "☰ منو" in body and "md:hidden" in body


def test_admin_login_is_throttled(client, db):
    User.objects.create_superuser("09120000001", "right-password-1")
    url = reverse("admin:login")
    for _ in range(MAX_FAILURES):
        client.post(url, {"username": "09120000001", "password": "wrong"})
    response = client.post(url, {"username": "09120000001", "password": "right-password-1"})
    assert response.status_code == 429
    assert "_auth_user_id" not in client.session


def test_bale_webhook_with_non_ascii_secret_is_404(client, db):
    response = client.post("/payments/bale/سلام/", "{}", content_type="application/json")
    assert response.status_code == 404


def test_sales_report(client, course):
    student = User.objects.create_user("09121111111")
    DiscountCode.objects.create(code="HALF", value=50)
    paid = services.create_order(student, course, "HALF")
    services.mark_paid(paid, Order.Method.CARD)
    old = services.create_order(User.objects.create_user("09122222222"), course)
    services.mark_paid(old, Order.Method.BALE)
    Order.objects.filter(pk=old.pk).update(paid_at=timezone.now() - timedelta(days=70))
    services.create_order(User.objects.create_user("09123333333"), course)  # unpaid

    report = build_report()
    assert report["all_time"] == {"revenue": 1_500_000, "count": 2}
    assert report["last_30"] == {"revenue": 500_000, "count": 1}
    assert report["by_type"]["دوره"]["revenue"] == 1_500_000
    assert len(report["monthly"]) == 12
    assert sum(m["revenue"] for m in report["monthly"]) == 1_500_000
    assert report["monthly"][-1]["revenue"] >= 500_000  # current Jalali month is last
    assert list(report["discounts"])[0]["discount_code__code"] == "HALF"
    assert {m["label"] for m in report["methods"]} == {"کارت‌به‌کارت", "پرداخت در بله"}

    client.force_login(User.objects.create_superuser("09120000001", "pass-12345"))
    page = client.get(reverse("admin_sales_report"))
    assert page.status_code == 200 and "درآمد ماهانه" in page.content.decode()
    assert "گزارش فروش" in client.get(reverse("admin:index")).content.decode()


def test_sales_report_requires_staff(client, db):
    client.force_login(User.objects.create_user("09121111111"))
    assert client.get(reverse("admin_sales_report")).status_code == 302
