import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_reports_db_ok(client):
    response = client.get(reverse("core:health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True}


@pytest.mark.django_db
def test_home_renders_rtl_persian_page(client):
    response = client.get(reverse("core:home"))
    assert response.status_code == 200
    assert 'dir="rtl"' in response.content.decode()


@pytest.mark.django_db
def test_admin_login_page_is_available(client, settings):
    response = client.get(f"/{settings.ADMIN_URL}login/")
    assert response.status_code == 200


def test_persian_filters():
    from datetime import date

    from apps.core.templatetags.fa import fa_num, jdate, toman

    assert fa_num(120) == "۱۲۰"
    assert toman(1500000) == "۱٬۵۰۰٬۰۰۰ تومان"
    assert toman(0) == "رایگان"
    assert jdate(date(2026, 3, 21)) == "۱۴۰۵/۰۱/۰۱"
