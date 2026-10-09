import logging

import requests
from django.conf import settings

from apps.siteconfig.models import SiteSettings

logger = logging.getLogger(__name__)

SMSIR_VERIFY_URL = "https://api.sms.ir/v1/send/verify"
# sms.ir rejects long parameter values in Verify templates.
MAX_PARAM_LENGTH = 25


class SMSError(Exception):
    """Raised when an SMS could not be sent; the message is safe to show to users."""


def send_template(phone: str, template_id: int, params: dict[str, str]) -> None:
    """Send an sms.ir Verify (template) message. Raises SMSError."""
    config = SiteSettings.load()
    if not config.sms_api_key or not template_id:
        if settings.DEBUG:
            logger.warning("SMS not configured; would send template %s to %s: %s",
                           template_id, phone, params)  # fmt: skip
            return
        raise SMSError("ارسال پیامک هنوز تنظیم نشده است. لطفاً با پشتیبانی تماس بگیرید.")

    payload = {
        "mobile": phone,
        "templateId": template_id,
        "parameters": [
            {"name": name, "value": str(value)[:MAX_PARAM_LENGTH]} for name, value in params.items()
        ],
    }
    try:
        response = requests.post(
            SMSIR_VERIFY_URL,
            json=payload,
            headers={"x-api-key": config.sms_api_key, "Accept": "application/json"},
            timeout=10,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("sms.ir request failed: %s", type(exc).__name__)
        raise SMSError("ارسال پیامک با خطا مواجه شد. چند لحظه بعد دوباره تلاش کنید.") from None

    if response.status_code != 200 or data.get("status") != 1:
        logger.error("sms.ir rejected template %s: %s %s", template_id, response.status_code, data)
        raise SMSError("ارسال پیامک با خطا مواجه شد. چند لحظه بعد دوباره تلاش کنید.")


def send_otp(phone: str, code: str) -> None:
    config = SiteSettings.load()
    if not config.sms_configured and settings.DEBUG:
        logger.warning("SMS not configured; OTP for %s is %s", phone, code)
        return
    send_template(phone, config.sms_otp_template_id, {config.sms_otp_param_name: code})
