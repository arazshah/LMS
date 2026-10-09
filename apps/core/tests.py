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
