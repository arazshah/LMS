import jdatetime
from django import template
from django.utils import timezone

register = template.Library()

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


@register.filter
def fa_num(value):
    """Render digits in Persian."""
    if value is None:
        return ""
    return str(value).translate(_FA_DIGITS)


@register.filter
def toman(value):
    """1500000 -> «۱٬۵۰۰٬۰۰۰ تومان»; 0 -> «رایگان»."""
    if not value:
        return "رایگان"
    return f"{int(value):,}".replace(",", "٬").translate(_FA_DIGITS) + " تومان"


@register.filter
def jdate(value, fmt="%Y/%m/%d"):
    """Format a date/datetime in the Jalali calendar with Persian digits."""
    if not value:
        return ""
    if hasattr(value, "tzinfo") and timezone.is_aware(value):
        value = timezone.localtime(value)
    if hasattr(value, "hour"):
        converted = jdatetime.datetime.fromgregorian(datetime=value)
    else:
        converted = jdatetime.date.fromgregorian(date=value)
    return converted.strftime(fmt).translate(_FA_DIGITS)


@register.filter
def money(value):
    """Amount in toman for reports: 0 -> «۰ تومان» (unlike `toman`, which says «رایگان»)."""
    return f"{int(value or 0):,}".replace(",", "٬").translate(_FA_DIGITS) + " تومان"
