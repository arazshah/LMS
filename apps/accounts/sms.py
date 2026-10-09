import logging

import requests
from django.conf import settings

from apps.siteconfig.models import SiteSettings

logger = logging.getLogger(__name__)

SMSIR_VERIFY_URL = "https://api.sms.ir/v1/send/verify"


class SMSError(Exception):
    """Raised when an SMS could not be sent; the message is safe to show to users."""


def send_otp(phone: str, code: str) -> None:
    config = SiteSettings.load()
    if not config.sms_configured:
        if settings.DEBUG:
            logger.warning("SMS not configured; OTP for %s is %s", phone, code)
            return
        raise SMSError("ارسال پیامک هنوز تنظیم نشده است. لطفاً با پشتیبانی تماس بگیرید.")

    payload = {
        "mobile": phone,
        "templateId": config.sms_otp_template_id,
        "parameters": [{"name": config.sms_otp_param_name, "value": code}],
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
        logger.exception("sms.ir request failed")
        raise SMSError("ارسال پیامک با خطا مواجه شد. چند لحظه بعد دوباره تلاش کنید.") from exc

    if response.status_code != 200 or data.get("status") != 1:
        logger.error("sms.ir rejected OTP: %s %s", response.status_code, data)
        raise SMSError("ارسال پیامک با خطا مواجه شد. چند لحظه بعد دوباره تلاش کنید.")
