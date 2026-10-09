import re

from django.core.exceptions import ValidationError

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_MOBILE_RE = re.compile(r"^09\d{9}$")


def normalize_phone(value: str) -> str:
    """Return an Iranian mobile number as 09XXXXXXXXX, or raise ValidationError."""
    phone = re.sub(r"[\s\-()]", "", str(value).translate(_DIGITS))
    if phone.startswith("+98"):
        phone = "0" + phone[3:]
    elif phone.startswith("0098"):
        phone = "0" + phone[4:]
    elif phone.startswith("98") and len(phone) == 12:
        phone = "0" + phone[2:]
    elif phone.startswith("9") and len(phone) == 10:
        phone = "0" + phone
    if not _MOBILE_RE.match(phone):
        raise ValidationError("شماره موبایل معتبر نیست.", code="invalid_phone")
    return phone
