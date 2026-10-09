import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import OTPCode
from .sms import send_otp

CODE_LENGTH = 5
CODE_TTL = timedelta(minutes=3)
RESEND_COOLDOWN = timedelta(minutes=2)
MAX_ATTEMPTS = 5
IP_LIMIT = 10  # codes per IP per window
IP_WINDOW_SECONDS = 60 * 60


class OTPError(Exception):
    pass


@dataclass
class SendResult:
    wait_seconds: int


def _hash(phone: str, code: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def seconds_until_resend(phone: str) -> int:
    # Only an unused code blocks a new one; after a successful login the user can
    # immediately request a fresh code (e.g. to sign in on another device).
    last = OTPCode.objects.filter(phone=phone, used=False).order_by("-created_at").first()
    if not last:
        return 0
    remaining = (last.created_at + RESEND_COOLDOWN - timezone.now()).total_seconds()
    return max(0, int(remaining))


def request_code(phone: str, ip: str | None) -> SendResult:
    """Create and send a login code. Raises OTPError/SMSError with a user-facing message."""
    wait = seconds_until_resend(phone)
    if wait:
        raise OTPError(f"لطفاً {wait} ثانیه دیگر برای دریافت کد جدید تلاش کنید.")

    if ip:
        ip_key = f"otp:ip:{ip}"
        cache.add(ip_key, 0, IP_WINDOW_SECONDS)
        if cache.incr(ip_key) > IP_LIMIT:
            raise OTPError("تعداد درخواست‌ها زیاد است. لطفاً بعداً تلاش کنید.")

    code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
    OTPCode.objects.filter(phone=phone, used=False).update(used=True)
    otp = OTPCode.objects.create(
        phone=phone, code_hash=_hash(phone, code), expires_at=timezone.now() + CODE_TTL
    )
    try:
        send_otp(phone, code)
    except Exception:
        otp.delete()  # don't start a cooldown for a code the user never received
        raise
    return SendResult(wait_seconds=int(RESEND_COOLDOWN.total_seconds()))


def verify_code(phone: str, code: str) -> None:
    """Consume a valid code or raise OTPError."""
    otp = (
        OTPCode.objects.filter(phone=phone, used=False, expires_at__gt=timezone.now())
        .order_by("-created_at")
        .first()
    )
    if otp is None:
        raise OTPError("کد منقضی شده است. لطفاً کد جدید دریافت کنید.")
    if otp.attempts >= MAX_ATTEMPTS:
        raise OTPError("تعداد تلاش‌های ناموفق زیاد بود. لطفاً کد جدید دریافت کنید.")

    otp.attempts += 1
    if not hmac.compare_digest(otp.code_hash, _hash(phone, code.strip())):
        otp.save(update_fields=["attempts"])
        raise OTPError("کد وارد شده صحیح نیست.")
    otp.used = True
    otp.save(update_fields=["attempts", "used"])
