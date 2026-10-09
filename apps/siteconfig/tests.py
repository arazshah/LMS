import pytest
from django.urls import reverse

from apps.accounts.models import User

from .models import SiteSettings


@pytest.mark.django_db
def test_settings_is_a_singleton_and_cache_is_refreshed():
    config = SiteSettings.load()
    config.site_name = "نام جدید"
    config.save()
    assert SiteSettings.objects.count() == 1
    assert SiteSettings.load().site_name == "نام جدید"


@pytest.mark.django_db
def test_admin_changelist_redirects_to_single_settings_page(client):
    client.force_login(User.objects.create_superuser("09120000001", "pass-12345"))
    response = client.get(reverse("admin:siteconfig_sitesettings_changelist"))
    assert response.url == reverse("admin:siteconfig_sitesettings_change", args=[1])
    assert client.get(response.url).status_code == 200


@pytest.mark.django_db
def test_site_name_is_rendered(client):
    config = SiteSettings.load()
    config.site_name = "آکادمی آراز"
    config.save()
    assert "آکادمی آراز" in client.get("/").content.decode()
