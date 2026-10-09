from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.notify.tasks import send_live_reminders
from apps.shop import services
from apps.shop.models import DiscountCode, Order
from apps.siteconfig.models import SiteSettings

from .models import LiveClass, LiveRegistration, LiveSession

MEET = "https://meet.google.com/abc-defg-hij"


@pytest.fixture
def live(db):
    return LiveClass.objects.create(
        title="کارگاه زنده GeoAI", price=900_000, capacity=2, is_published=True
    )


def add_session(live, starts_in, **kw):
    return LiveSession.objects.create(
        live_class=live,
        title=kw.pop("title", "جلسه"),
        starts_at=timezone.now() + starts_in,
        meet_link=kw.pop("meet_link", MEET),
        **kw,
    )


@pytest.fixture
def user(db):
    return User.objects.create_user("09121111111", first_name="سارا")


@pytest.fixture
def sms_config(db):
    config = SiteSettings.load()
    config.sms_api_key = "KEY"
    config.sms_otp_template_id = 1
    config.sms_paid_template_id = 11
    config.sms_rejected_template_id = 12
    config.sms_reminder_template_id = 13
    config.save()
    return config


@pytest.fixture
def sent():
    calls = []
    with mock.patch("apps.notify.tasks.send_template", side_effect=lambda *a: calls.append(a)):
        yield calls


def register(user, live):
    order = services.create_order(user, live)
    services.mark_paid(order, Order.Method.CARD)
    return order


# --- purchase ------------------------------------------------------------------


def test_paying_registers_user(user, live):
    order = register(user, live)
    registration = LiveRegistration.objects.get(user=user, live_class=live)
    assert registration.order == order
    assert live.is_registered(user) and live.seats_left == 1
    assert order.product_kind_label == "کلاس زنده"


def test_cannot_register_twice_or_when_full(user, live):
    register(user, live)
    with pytest.raises(services.ShopError, match="قبلاً"):
        services.create_order(user, live)
    register(User.objects.create_user("09122222222"), live)
    with pytest.raises(services.ShopError, match="ظرفیت"):
        services.create_order(User.objects.create_user("09123333333"), live)


def test_discount_can_target_live_class(user, live):
    code = DiscountCode.objects.create(code="LIVE50", value=50)
    code.live_classes.add(live)
    assert services.quote(user, live, "live50").total == 450_000


def test_checkout_page_for_live_class(client, user, live):
    client.force_login(user)
    response = client.post(reverse("shop:checkout", args=["live", live.slug]), {"action": "pay"})
    order = Order.objects.get()
    assert order.live_class == live and response.url == order.get_absolute_url()


# --- meet link visibility --------------------------------------------------------


def test_meet_link_only_for_registered_users_inside_join_window(client, user, live):
    soon = add_session(live, timedelta(minutes=10), title="شروع نزدیک")
    later = add_session(live, timedelta(days=2), title="هفته بعد", meet_link=MEET + "-2")
    url = live.get_absolute_url()

    body = client.get(url).content.decode()
    assert MEET not in body and "ثبت‌نام در کلاس" in body

    client.force_login(user)
    assert MEET not in client.get(url).content.decode()

    register(user, live)
    body = client.get(url).content.decode()
    assert soon.meet_link in body  # starts in 10 min: inside the 15-minute window
    assert later.meet_link not in body
    assert "۱۵ دقیقه قبل از شروع" in body


def test_finished_session_hides_link(client, user, live):
    add_session(live, -timedelta(hours=3), duration_minutes=60)
    register(user, live)
    client.force_login(user)
    body = client.get(live.get_absolute_url()).content.decode()
    assert MEET not in body and "برگزار شد" in body


def test_pages_list_and_my_courses(client, user, live):
    add_session(live, timedelta(days=1))
    assert live.title in client.get(reverse("live:list")).content.decode()
    assert live.title in client.get(reverse("core:home")).content.decode()
    hidden = LiveClass.objects.create(title="پیش‌نویس", price=1)
    assert client.get(hidden.get_absolute_url()).status_code == 404

    register(user, live)
    client.force_login(user)
    body = client.get(reverse("catalog:my_courses")).content.decode()
    assert "کلاس‌های زنده من" in body and live.title in body


def test_admin_pages(client, live):
    add_session(live, timedelta(days=1))
    client.force_login(User.objects.create_superuser("09120000001", "pass-12345"))
    for url in [
        reverse("admin:live_liveclass_changelist"),
        reverse("admin:live_liveclass_change", args=[live.pk]),
        reverse("admin:live_liveregistration_add"),
    ]:
        assert client.get(url).status_code == 200, url


# --- SMS notifications -------------------------------------------------------------


def test_payment_and_rejection_sms(
    user, live, sms_config, sent, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        order = register(user, live)
    assert sent == [("09121111111", 11, {"ORDER": order.number, "TITLE": live.title})]

    other = User.objects.create_user("09122222222")
    order2 = services.create_order(other, live)
    order2.mark_receipt_submitted()
    order2.save()
    with django_capture_on_commit_callbacks(execute=True):
        services.reject_receipt(order2)
    assert sent[-1] == ("09122222222", 12, {"ORDER": order2.number})


def test_no_sms_when_template_not_set(
    user, live, sms_config, sent, django_capture_on_commit_callbacks
):
    sms_config.sms_paid_template_id = None
    sms_config.save()
    with django_capture_on_commit_callbacks(execute=True):
        register(user, live)
    assert sent == []


def test_free_order_sends_no_payment_sms(
    user, live, sms_config, sent, django_capture_on_commit_callbacks
):
    DiscountCode.objects.create(code="FREE", value=100)
    with django_capture_on_commit_callbacks(execute=True):
        order = services.create_order(user, live, "free")
    assert order.is_paid and sent == []


def test_live_reminders_day_and_hour_sent_once(user, live, sms_config, sent):
    register(user, live)
    register(User.objects.create_user("09122222222"), live)
    tomorrow = add_session(live, timedelta(hours=23))
    soon = add_session(live, timedelta(minutes=40))
    add_session(live, timedelta(days=3))  # too far

    assert send_live_reminders() == 4  # 2 users x (tomorrow day-reminder + soon hour-reminder)
    assert send_live_reminders() == 0  # already sent
    tomorrow.refresh_from_db()
    soon.refresh_from_db()
    assert tomorrow.reminder_day_sent_at and not tomorrow.reminder_hour_sent_at
    assert soon.reminder_hour_sent_at and not soon.reminder_day_sent_at
    phone, template, params = sent[0]
    assert template == 13 and params["TITLE"] == live.title
    assert params["TIME"].count(":") == 1  # Jalali date + HH:MM


def test_unpublished_class_gets_no_reminders(user, live, sms_config, sent):
    register(user, live)
    live.is_published = False
    live.save()
    add_session(live, timedelta(minutes=30))
    assert send_live_reminders() == 0


def test_sms_parameters_are_truncated_for_sms_ir(sms_config):
    from apps.accounts import sms

    response = mock.Mock(status_code=200)
    response.json.return_value = {"status": 1}
    with mock.patch("apps.accounts.sms.requests.post", return_value=response) as post:
        sms.send_template("09121111111", 13, {"TITLE": "ا" * 60})
    value = post.call_args.kwargs["json"]["parameters"][0]["value"]
    assert len(value) == sms.MAX_PARAM_LENGTH
