from datetime import timedelta
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Category, Course, Enrollment
from apps.siteconfig.models import SiteSettings

from . import bale, services
from .models import Bundle, DiscountCode, Order


def _png() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, "PNG")
    return buf.getvalue()


PNG = _png()


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def category(db):
    return Category.objects.create(title="GeoAI")


@pytest.fixture
def course(category):
    return Course.objects.create(
        category=category, title="دوره اصلی", price=1_000_000, access_days=180, is_published=True
    )


@pytest.fixture
def course2(category):
    return Course.objects.create(
        category=category, title="دوره دوم", price=600_000, access_days=None, is_published=True
    )


@pytest.fixture
def bundle(course, course2):
    b = Bundle.objects.create(title="پکیج کامل", price=1_200_000, is_published=True)
    b.courses.set([course, course2])
    return b


@pytest.fixture
def user(db):
    return User.objects.create_user("09121111111", first_name="سارا", last_name="محمدی")


@pytest.fixture
def config(db):
    c = SiteSettings.load()
    c.card_number = "6037-9911-1111-2222"
    c.card_holder = "آراز"
    c.bale_bot_token = "TOKEN"
    c.bale_bot_username = "araz_lms_bot"
    c.bale_provider_token = "6037991111112222"
    c.save()
    return c


def code(**kw):
    defaults = {"code": "geo20", "kind": DiscountCode.Kind.PERCENT, "value": 20}
    return DiscountCode.objects.create(**{**defaults, **kw})


# --- discounts --------------------------------------------------------------


def test_percent_fixed_and_cap(user, course):
    code()
    assert services.quote(user, course, "GEO20").discount == 200_000
    code(code="CAP", max_discount=50_000)
    assert services.quote(user, course, "cap").discount == 50_000
    code(code="FIX", kind=DiscountCode.Kind.FIXED, value=300_000)
    assert services.quote(user, course, "fix").total == 700_000
    code(code="BIG", kind=DiscountCode.Kind.FIXED, value=5_000_000)
    assert services.quote(user, course, "big").total == 0


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"is_active": False}, "معتبر نیست"),
        ({"valid_until": timezone.now() - timedelta(days=1)}, "تمام شده"),
        ({"valid_from": timezone.now() + timedelta(days=1)}, "شروع نشده"),
        ({"min_amount": 2_000_000}, "کافی نیست"),
    ],
)
def test_invalid_codes(user, course, kwargs, message):
    code(**kwargs)
    with pytest.raises(services.ShopError, match=message):
        services.quote(user, course, "GEO20")


def test_code_usage_limits(user, course, course2):
    c = code(max_uses=1)
    order = services.create_order(user, course, "GEO20")
    services.mark_paid(order, Order.Method.CARD)
    other = User.objects.create_user("09122222222")
    with pytest.raises(services.ShopError, match="ظرفیت"):
        services.quote(other, course2, "GEO20")
    c.max_uses = None
    c.save()
    with pytest.raises(services.ShopError, match="قبلاً"):
        services.quote(user, course2, "GEO20")
    assert services.quote(other, course2, "GEO20").discount == 120_000


def test_code_restricted_to_products(user, course, course2, bundle):
    c = code()
    c.courses.add(course)
    assert services.quote(user, course, "GEO20").discount
    with pytest.raises(services.ShopError, match="این محصول"):
        services.quote(user, course2, "GEO20")
    with pytest.raises(services.ShopError):
        services.quote(user, bundle, "GEO20")
    c.bundles.add(bundle)
    assert services.quote(user, bundle, "GEO20").discount == 240_000


# --- purchase rules and access ---------------------------------------------


def test_cannot_buy_free_unpublished_or_owned_forever(user, course, course2):
    course.price = 0
    course.save()
    with pytest.raises(services.ShopError, match="رایگان"):
        services.create_order(user, course)
    course2.is_published = False
    course2.save()
    with pytest.raises(services.ShopError):
        services.create_order(user, course2)
    course2.is_published = True
    course2.save()
    Enrollment.objects.create(user=user, course=course2)  # access_days=None -> unlimited
    with pytest.raises(services.ShopError, match="دائمی"):
        services.create_order(user, course2)


def test_paid_course_order_grants_timed_access(user, course):
    order = services.create_order(user, course)
    assert order.number == str(1000 + order.pk) and order.status == Order.Status.PENDING
    assert services.mark_paid(order, Order.Method.CARD) is True
    assert services.mark_paid(order, Order.Method.CARD) is False  # idempotent
    enrollment = Enrollment.objects.get(user=user, course=course)
    assert enrollment.order == order and enrollment.source == Enrollment.Source.ORDER
    assert (enrollment.expires_at - enrollment.starts_at).days == 180
    assert course.has_access(user)


def test_renewal_extends_existing_access(user, course):
    first = Enrollment.objects.create(user=user, course=course)
    order = services.create_order(user, course)
    services.mark_paid(order, Order.Method.BALE)
    renewal = Enrollment.objects.filter(order=order).get()
    assert renewal.starts_at == first.expires_at
    assert renewal.expires_at == first.expires_at + timedelta(days=180)


def test_bundle_grants_every_course(user, bundle, course, course2):
    order = services.create_order(user, bundle)
    services.mark_paid(order, Order.Method.CARD)
    timed = Enrollment.objects.get(user=user, course=course)
    unlimited = Enrollment.objects.get(user=user, course=course2)
    assert (timed.expires_at - timed.starts_at).days == 180
    assert unlimited.expires_at is None

    bundle.access_days = 30
    bundle.save()
    other = User.objects.create_user("09122222222")
    services.mark_paid(services.create_order(other, bundle), Order.Method.CARD)
    for e in Enrollment.objects.filter(user=other):
        assert (e.expires_at - e.starts_at).days == 30


def test_full_discount_order_is_paid_immediately(user, course):
    code(value=100)
    order = services.create_order(user, course, "GEO20")
    assert order.is_paid and order.payment_method == Order.Method.FREE
    assert course.has_access(user)


def test_cancelled_order_cannot_be_paid(user, course):
    order = services.create_order(user, course)
    order.status = Order.Status.CANCELLED
    order.save()
    with pytest.raises(services.ShopError):
        services.mark_paid(order, Order.Method.CARD)


# --- buyer pages ------------------------------------------------------------


def test_checkout_requires_login(client, course):
    response = client.get(reverse("shop:checkout", args=["course", course.slug]))
    assert response.status_code == 302 and "/accounts/login/" in response.url


def test_checkout_apply_code_then_pay(client, user, course):
    code()
    client.force_login(user)
    url = reverse("shop:checkout", args=["course", course.slug])
    response = client.post(url, {"code": "geo20", "action": "apply"})
    assert response.context["quote"].total == 800_000
    assert not Order.objects.exists()

    response = client.post(url, {"code": "geo20", "action": "pay"})
    order = Order.objects.get()
    assert response.url == order.get_absolute_url()
    assert (order.total, order.discount_code.code) == (800_000, "GEO20")


def test_checkout_with_bad_code_does_not_create_order(client, user, course):
    client.force_login(user)
    url = reverse("shop:checkout", args=["course", course.slug])
    response = client.post(url, {"code": "nope", "action": "pay"})
    assert "کد تخفیف معتبر نیست" in response.content.decode()
    assert response.context["quote"].total == 1_000_000
    assert not Order.objects.exists()


def test_checkout_bundle_and_404_for_unknown_kind(client, user, bundle):
    client.force_login(user)
    assert client.get(reverse("shop:checkout", args=["bundle", bundle.slug])).status_code == 200
    assert client.get(reverse("shop:checkout", args=["x", bundle.slug])).status_code == 404


def test_payment_page_shows_both_methods(client, user, course, config):
    order = services.create_order(user, course)
    client.force_login(user)
    body = client.get(order.get_absolute_url()).content.decode()
    assert f"https://ble.ir/araz_lms_bot?start={order.token.hex}" in body
    assert "6037-9911-1111-2222" in body


def test_payment_page_is_private(client, user, course):
    order = services.create_order(user, course)
    client.force_login(User.objects.create_user("09122222222"))
    assert client.get(order.get_absolute_url()).status_code == 404


def test_receipt_upload_and_review_flow(client, user, course, config):
    order = services.create_order(user, course)
    client.force_login(user)
    response = client.post(
        order.get_absolute_url(),
        {"receipt": SimpleUploadedFile("r.png", PNG, "image/png"), "receipt_ref": "123456"},
    )
    assert response.status_code == 302
    order.refresh_from_db()
    assert order.status == Order.Status.AWAITING_REVIEW and order.receipt
    assert order.receipt.name.startswith("protected/receipts/")

    services.reject_receipt(order, "مبلغ کمتر واریز شده")
    order.refresh_from_db()
    assert order.status == Order.Status.REJECTED and order.can_pay
    body = client.get(order.get_absolute_url()).content.decode()
    assert "مبلغ کمتر واریز شده" in body


def test_receipt_must_be_an_image(client, user, course, config):
    order = services.create_order(user, course)
    client.force_login(user)
    client.post(order.get_absolute_url(), {"receipt": SimpleUploadedFile("r.png", b"nope")})
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING


def test_status_poll_redirects_when_paid(client, user, course):
    order = services.create_order(user, course)
    client.force_login(user)
    url = reverse("shop:order_status", args=[order.number])
    assert client.get(url).status_code == 204
    services.mark_paid(order, Order.Method.BALE)
    assert client.get(url)["HX-Redirect"] == order.get_absolute_url()


def test_invoice_pdf_only_for_paid_orders(client, user, course):
    order = services.create_order(user, course)
    client.force_login(user)
    url = reverse("shop:order_invoice", args=[order.number])
    assert client.get(url).status_code == 404
    services.mark_paid(order, Order.Method.CARD)
    response = client.get(url)
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_receipt_image_only_for_staff(client, user, course, config):
    order = services.create_order(user, course)
    order.receipt = SimpleUploadedFile("r.png", PNG, "image/png")
    order.save()
    url = reverse("shop:order_receipt", args=[order.number])
    client.force_login(user)
    assert client.get(url).status_code == 404
    client.force_login(User.objects.create_superuser("09120000001", "pass-12345"))
    assert client.get(url).status_code == 200


def test_order_list_and_bundle_pages(client, user, course, bundle):
    services.create_order(user, course)
    client.force_login(user)
    assert course.title in client.get(reverse("shop:order_list")).content.decode()
    assert bundle.title in client.get(reverse("shop:bundle_list")).content.decode()
    body = client.get(bundle.get_absolute_url()).content.decode()
    assert course.title in body and "خرید پکیج" in body
    course_page = client.get(course.get_absolute_url()).content.decode()
    assert "خرید دوره" in course_page and bundle.title in course_page


# --- admin --------------------------------------------------------------------


@pytest.fixture
def admin_client(client, db):
    client.force_login(User.objects.create_superuser("09120000001", "pass-12345"))
    return client


def test_admin_approve_and_reject_actions(admin_client, user, course, course2):
    a = services.create_order(user, course)
    b = services.create_order(user, course2)
    for o in (a, b):
        o.mark_receipt_submitted()
        o.save()
    url = reverse("admin:shop_order_changelist")
    admin_client.post(url, {"action": "approve", "_selected_action": [a.pk]})
    admin_client.post(url, {"action": "reject", "_selected_action": [b.pk]})
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.is_paid and a.payment_method == Order.Method.CARD
    assert course.has_access(user)
    assert b.status == Order.Status.REJECTED and not course2.has_access(user)


def test_admin_pages_load(admin_client, user, course, bundle, config):
    order = services.create_order(user, course)
    order.mark_receipt_submitted()
    order.receipt = SimpleUploadedFile("r.png", PNG, "image/png")
    order.save()
    code()
    index = admin_client.get(reverse("admin:index")).content.decode()
    assert "رسید کارت‌به‌کارت منتظر بررسی" in index
    for url in [
        reverse("admin:shop_order_change", args=[order.pk]),
        reverse("admin:shop_order_changelist"),
        reverse("admin:shop_bundle_change", args=[bundle.pk]),
        reverse("admin:shop_discountcode_changelist"),
        reverse("admin:shop_discountcode_add"),
        reverse("admin:siteconfig_sitesettings_change", args=[1]),
    ]:
        assert admin_client.get(url).status_code == 200, url


def test_admin_connect_bale_sets_webhook(admin_client, config):
    with mock.patch("apps.shop.bale.call") as call:
        admin_client.post(reverse("admin:siteconfig_connect_bale"))
    method, payload = call.call_args.args
    assert method == "setWebhook"
    assert payload["url"].endswith(f"/payments/bale/{config.bale_webhook_secret}/")


# --- Bale bot -----------------------------------------------------------------


@pytest.fixture
def bale_calls(config):
    calls = []
    with mock.patch("apps.shop.bale.call", side_effect=lambda m, p: calls.append((m, p)) or {}):
        yield calls


def _webhook(client, update, secret=None):
    secret = secret or SiteSettings.load().bale_webhook_secret
    return client.post(
        reverse("shop:bale_webhook", args=[secret]), update, content_type="application/json"
    )


def test_webhook_rejects_wrong_secret(client, config):
    assert _webhook(client, {}, secret="wrong").status_code == 404


def test_start_with_token_sends_invoice(client, user, course, bale_calls):
    order = services.create_order(user, course, "")
    msg = {"message": {"chat": {"id": 42}, "text": f"/start {order.token.hex}"}}
    assert _webhook(client, msg).status_code == 200
    method, payload = bale_calls[-1]
    assert method == "sendInvoice"
    assert payload["chat_id"] == 42
    assert payload["payload"] == order.token.hex
    assert payload["provider_token"] == "6037991111112222"
    assert payload["prices"] == [{"label": course.title, "amount": 10_000_000}]  # rial
    order.refresh_from_db()
    assert order.bale_chat_id == "42"


def test_order_number_text_also_sends_invoice(client, user, course, bale_calls):
    order = services.create_order(user, course)
    _webhook(client, {"message": {"chat": {"id": 7}, "text": f"سفارش {order.number}"}})
    assert bale_calls[-1][0] == "sendInvoice"


def test_unknown_text_gets_help(client, config, bale_calls):
    _webhook(client, {"message": {"chat": {"id": 7}, "text": "سلام"}})
    assert bale_calls[-1][0] == "sendMessage"


def test_pre_checkout_validation(client, user, course, bale_calls):
    order = services.create_order(user, course)
    q = {"id": "q1", "invoice_payload": order.token.hex, "total_amount": 10_000_000}
    _webhook(client, {"pre_checkout_query": q})
    assert bale_calls[-1] == ("answerPreCheckoutQuery", {"pre_checkout_query_id": "q1", "ok": True})

    _webhook(client, {"pre_checkout_query": {**q, "total_amount": 5}})
    assert bale_calls[-1][1]["ok"] is False

    services.mark_paid(order, Order.Method.CARD)
    _webhook(client, {"pre_checkout_query": q})
    assert bale_calls[-1][1]["ok"] is False


def test_successful_payment_marks_order_paid_once(client, user, course, bale_calls):
    order = services.create_order(user, course)
    update = {
        "message": {
            "chat": {"id": 42},
            "successful_payment": {
                "currency": "IRR",
                "total_amount": 10_000_000,
                "invoice_payload": order.token.hex,
                "provider_payment_charge_id": "TX-1",
            },
        }
    }
    _webhook(client, update)
    _webhook(client, update)  # duplicate delivery
    order.refresh_from_db()
    assert order.is_paid and order.payment_method == Order.Method.BALE
    assert order.payment_ref == "TX-1"
    assert Enrollment.objects.filter(user=user, course=course).count() == 1
    assert [m for m, _ in bale_calls].count("sendMessage") == 1


def test_successful_payment_with_wrong_amount_is_not_accepted(client, user, course, bale_calls):
    order = services.create_order(user, course)
    update = {
        "message": {
            "chat": {"id": 42},
            "successful_payment": {"total_amount": 1000, "payload": order.token.hex},
        }
    }
    _webhook(client, update)
    order.refresh_from_db()
    assert not order.is_paid and "مغایرت" in order.admin_note


def test_bale_api_client(config):
    response = mock.Mock(status_code=200)
    response.json.return_value = {"ok": True, "result": {"message_id": 1}}
    with mock.patch("apps.shop.bale.requests.post", return_value=response) as post:
        assert bale.call("sendMessage", {"chat_id": 1, "text": "x"}) == {"message_id": 1}
    assert post.call_args.args[0] == "https://tapi.bale.ai/botTOKEN/sendMessage"

    response.json.return_value = {"ok": False, "description": "Unauthorized"}
    with mock.patch("apps.shop.bale.requests.post", return_value=response):
        with pytest.raises(bale.BaleError, match="Unauthorized"):
            bale.call("getMe", {})


def test_admin_order_page_buttons(admin_client, user, course):
    order = services.create_order(user, course)
    order.mark_receipt_submitted()
    order.save()
    page = admin_client.get(reverse("admin:shop_order_change", args=[order.pk])).content.decode()
    assert 'form="approve-form"' in page and 'id="approve-form"' in page
    # The approve/reject forms must not swallow the main form's save buttons.
    assert page.index('name="_save"') < page.index('id="approve-form"')

    admin_client.post(reverse("admin:shop_order_reject", args=[order.pk]), {"note": "ناخوانا"})
    order.refresh_from_db()
    assert order.status == Order.Status.REJECTED and order.admin_note == "ناخوانا"

    admin_client.post(reverse("admin:shop_order_approve", args=[order.pk]))
    order.refresh_from_db()
    assert order.is_paid and course.has_access(user)


def test_bale_errors_never_log_the_bot_token(config, caplog):
    import requests

    with mock.patch(
        "apps.shop.bale.requests.post",
        side_effect=requests.ConnectionError("https://tapi.bale.ai/botTOKEN/sendMessage"),
    ):
        bale.send_message(1, "x")
    assert "TOKEN" not in caplog.text and "ارتباط با سرور بله" in caplog.text
