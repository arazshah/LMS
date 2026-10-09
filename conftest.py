import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    """Cached rows (e.g. SiteSettings) must not leak between tests' rolled-back DBs."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
