from datetime import timedelta
from unittest import mock

import pytest
import requests
from django.urls import reverse
from django.utils import timezone

from apps.accounts import otp
from apps.accounts.models import OTPCode, User
from apps.accounts.sms import SMSError, send_otp
from apps.siteconfig.models import SiteSettings

PHONE = "09121234567"


@pytest.fixture
def sent_codes():
    """Capture codes instead of sending SMS."""
    codes = []
    with mock.patch("apps.accounts.otp.send_otp", side_effect=lambda p, c: codes.append(c)):
        yield codes


def _login_until_verify(client, phone=PHONE, next_url=None):
    url = reverse("accounts:login")
    if next_url:
        url += f"?next={next_url}"
    return client.post(url, {"phone": phone})


@pytest.mark.django_db
def test_full_login_creates_user_and_asks_for_name(client, sent_codes):
    response = _login_until_verify(client, "+98 912 123 4567", next_url="/courses/")
    assert response.url == reverse("accounts:verify")
    assert len(sent_codes) == 1 and len(sent_codes[0]) == otp.CODE_LENGTH

    response = client.post(reverse("accounts:verify"), {"code": sent_codes[0]})
    user = User.objects.get(phone=PHONE)
    assert int(client.session["_auth_user_id"]) == user.pk
    assert response.url == reverse("accounts:profile") + "?next=%2Fcourses%2F"

    response = client.post(response.url, {"first_name": "آرش", "last_name": "رضایی"})
    assert response.url == "/courses/"
    user.refresh_from_db()
    assert user.get_full_name() == "آرش رضایی"


@pytest.mark.django_db
def test_returning_user_with_name_goes_to_next(client, sent_codes):
    User.objects.create_user(PHONE, first_name="سارا")
    _login_until_verify(client, next_url="/courses/")
    response = client.post(reverse("accounts:verify"), {"code": sent_codes[0]})
    assert response.url == "/courses/"


@pytest.mark.django_db
def test_unsafe_next_is_ignored(client, sent_codes):
    User.objects.create_user(PHONE, first_name="سارا")
    _login_until_verify(client, next_url="https://evil.example/")
    response = client.post(reverse("accounts:verify"), {"code": sent_codes[0]})
    assert response.url == reverse("catalog:my_courses")


@pytest.mark.django_db
def test_persian_digits_in_code_are_accepted(client, sent_codes):
    _login_until_verify(client)
    persian = sent_codes[0].translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    client.post(reverse("accounts:verify"), {"code": persian})
    assert "_auth_user_id" in client.session


@pytest.mark.django_db
def test_wrong_code_is_rejected_and_attempts_are_limited(client, sent_codes):
    _login_until_verify(client)
    wrong = "00000" if sent_codes[0] != "00000" else "11111"
    for _ in range(otp.MAX_ATTEMPTS):
        response = client.post(reverse("accounts:verify"), {"code": wrong})
        assert "کد وارد شده صحیح نیست" in response.content.decode()
    response = client.post(reverse("accounts:verify"), {"code": sent_codes[0]})
    assert "_auth_user_id" not in client.session
    assert "تعداد تلاش‌های ناموفق" in response.content.decode()


@pytest.mark.django_db
def test_expired_code_is_rejected(client, sent_codes):
    _login_until_verify(client)
    OTPCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    response = client.post(reverse("accounts:verify"), {"code": sent_codes[0]})
    assert "_auth_user_id" not in client.session
    assert "منقضی" in response.content.decode()


@pytest.mark.django_db
def test_code_cannot_be_reused(sent_codes):
    otp.request_code(PHONE, None)
    otp.verify_code(PHONE, sent_codes[0])
    with pytest.raises(otp.OTPError):
        otp.verify_code(PHONE, sent_codes[0])


@pytest.mark.django_db
def test_resend_has_cooldown_and_old_code_stops_working(client, sent_codes):
    _login_until_verify(client)
    client.post(reverse("accounts:verify"), {"action": "resend"})
    assert len(sent_codes) == 1  # still cooling down

    OTPCode.objects.update(created_at=timezone.now() - otp.RESEND_COOLDOWN)
    client.post(reverse("accounts:verify"), {"action": "resend"})
    assert len(sent_codes) == 2
    old, new = OTPCode.objects.order_by("created_at")
    assert old.used and not new.used
    otp.verify_code(PHONE, sent_codes[1])


@pytest.mark.django_db
def test_second_login_request_within_cooldown_goes_to_verify(client, sent_codes):
    _login_until_verify(client)
    client.session.flush()
    response = _login_until_verify(client)
    assert response.url == reverse("accounts:verify")
    assert len(sent_codes) == 1


@pytest.mark.django_db
def test_ip_rate_limit(sent_codes):
    for i in range(otp.IP_LIMIT):
        otp.request_code(f"0912000{i:04d}", "1.2.3.4")
    with pytest.raises(otp.OTPError):
        otp.request_code("09129999999", "1.2.3.4")


@pytest.mark.django_db
def test_sms_failure_shows_error_and_allows_retry(client):
    with mock.patch("apps.accounts.otp.send_otp", side_effect=SMSError("خطای پیامک")):
        response = _login_until_verify(client)
    assert response.status_code == 200
    assert "خطای پیامک" in response.content.decode()
    assert not OTPCode.objects.exists()


@pytest.mark.django_db
def test_inactive_user_cannot_log_in(client, sent_codes):
    User.objects.create_user(PHONE, is_active=False)
    _login_until_verify(client)
    response = client.post(reverse("accounts:verify"), {"code": sent_codes[0]})
    assert "_auth_user_id" not in client.session
    assert "غیرفعال" in response.content.decode()


@pytest.mark.django_db
def test_invalid_phone_shows_error(client):
    response = client.post(reverse("accounts:login"), {"phone": "12345"})
    assert "شماره موبایل معتبر نیست" in response.content.decode()


@pytest.mark.django_db
def test_logout(client):
    client.force_login(User.objects.create_user(PHONE))
    client.post(reverse("accounts:logout"))
    assert "_auth_user_id" not in client.session


# --- sms.ir client ---------------------------------------------------------


def _configure_sms():
    config = SiteSettings.load()
    config.sms_api_key = "KEY"
    config.sms_otp_template_id = 123456
    config.save()


@pytest.mark.django_db
def test_sms_ir_verify_request_payload():
    _configure_sms()
    response = mock.Mock(status_code=200)
    response.json.return_value = {"status": 1, "message": "موفق", "data": {}}
    with mock.patch("apps.accounts.sms.requests.post", return_value=response) as post:
        send_otp(PHONE, "12345")
    post.assert_called_once()
    _, kwargs = post.call_args
    assert post.call_args.args[0] == "https://api.sms.ir/v1/send/verify"
    assert kwargs["headers"]["x-api-key"] == "KEY"
    assert kwargs["json"] == {
        "mobile": PHONE,
        "templateId": 123456,
        "parameters": [{"name": "CODE", "value": "12345"}],
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status_code,body", [(400, {"status": 0, "message": "خطا"}), (200, {"status": 10})]
)
def test_sms_ir_error_response_raises(status_code, body):
    _configure_sms()
    response = mock.Mock(status_code=status_code)
    response.json.return_value = body
    with mock.patch("apps.accounts.sms.requests.post", return_value=response):
        with pytest.raises(SMSError):
            send_otp(PHONE, "12345")


@pytest.mark.django_db
def test_sms_ir_network_error_raises():
    _configure_sms()
    with mock.patch(
        "apps.accounts.sms.requests.post", side_effect=requests.ConnectionError("down")
    ):
        with pytest.raises(SMSError):
            send_otp(PHONE, "12345")


@pytest.mark.django_db
def test_sms_not_configured_raises_in_production(settings):
    settings.DEBUG = False
    with pytest.raises(SMSError):
        send_otp(PHONE, "12345")


@pytest.mark.django_db
def test_sms_not_configured_logs_code_in_debug(settings, caplog):
    settings.DEBUG = True
    send_otp(PHONE, "12345")
    assert "12345" in caplog.text


@pytest.mark.django_db
def test_used_code_does_not_block_a_new_login(client, sent_codes):
    _login_until_verify(client)
    client.post(reverse("accounts:verify"), {"code": sent_codes[0]})
    client.post(reverse("accounts:logout"))
    _login_until_verify(client)
    assert len(sent_codes) == 2
    client.post(reverse("accounts:verify"), {"code": sent_codes[1]})
    assert "_auth_user_id" in client.session
