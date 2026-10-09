"""Order lifecycle: pricing, discount validation, payment and access granting."""

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Course, Enrollment
from apps.live.models import LiveClass, LiveRegistration
from apps.notify import tasks as notify

from .models import Bundle, DiscountCode, Order


class ShopError(Exception):
    """Error with a message that is safe to show to the buyer."""


@dataclass
class Quote:
    amount: int
    discount: int
    code: DiscountCode | None

    @property
    def total(self):
        return self.amount - self.discount


def _product_fields(product):
    if isinstance(product, Course):
        return {"course": product}
    if isinstance(product, Bundle):
        return {"bundle": product}
    if isinstance(product, LiveClass):
        return {"live_class": product}
    raise TypeError(product)


def check_can_buy(user, product) -> None:
    if not product.is_published:
        raise ShopError("این محصول در حال حاضر فروخته نمی‌شود.")
    if isinstance(product, Course):
        if product.is_free:
            raise ShopError("این دوره رایگان است و نیازی به خرید ندارد.")
        unlimited = Enrollment.objects.active().filter(
            user=user, course=product, expires_at__isnull=True
        )
        if unlimited.exists():
            raise ShopError("شما دسترسی دائمی به این دوره دارید.")
    if isinstance(product, LiveClass):
        if product.registrations.filter(user=user).exists():
            raise ShopError("شما قبلاً در این کلاس ثبت‌نام کرده‌اید.")
        if product.is_full:
            raise ShopError("ظرفیت این کلاس تکمیل شده است.")


def validate_code(raw_code: str, user, product) -> DiscountCode:
    code = DiscountCode.objects.filter(code=raw_code.strip().upper(), is_active=True).first()
    now = timezone.now()
    if code is None:
        raise ShopError("کد تخفیف معتبر نیست.")
    if code.valid_from and now < code.valid_from:
        raise ShopError("زمان استفاده از این کد تخفیف هنوز شروع نشده است.")
    if code.valid_until and now > code.valid_until:
        raise ShopError("مهلت استفاده از این کد تخفیف تمام شده است.")
    if code.max_uses is not None and code.used_count >= code.max_uses:
        raise ShopError("ظرفیت استفاده از این کد تخفیف تمام شده است.")
    if code.one_per_user and code.orders.filter(user=user, status=Order.Status.PAID).exists():
        raise ShopError("شما قبلاً از این کد تخفیف استفاده کرده‌اید.")
    restricted = code.courses.exists() or code.bundles.exists() or code.live_classes.exists()
    if restricted:
        related = {Course: code.courses, Bundle: code.bundles, LiveClass: code.live_classes}
        if not related[type(product)].filter(pk=product.pk).exists():
            raise ShopError("این کد تخفیف برای این محصول قابل استفاده نیست.")
    if product.price < code.min_amount:
        raise ShopError("مبلغ خرید برای استفاده از این کد کافی نیست.")
    return code


def quote(user, product, raw_code: str = "") -> Quote:
    code = validate_code(raw_code, user, product) if raw_code.strip() else None
    discount = code.discount_for(product.price) if code else 0
    return Quote(amount=product.price, discount=discount, code=code)


def create_order(user, product, raw_code: str = "") -> Order:
    check_can_buy(user, product)
    q = quote(user, product, raw_code)
    order = Order.objects.create(
        user=user,
        title=product.title,
        amount=q.amount,
        discount_code=q.code,
        discount_amount=q.discount,
        total=q.total,
        **_product_fields(product),
    )
    if order.total == 0:
        mark_paid(order, Order.Method.FREE)
    return order


def grant_access(user, course: Course, days: int | None, order: Order | None = None):
    """Give access for `days` (None = unlimited); extends an active timed access."""
    active = (
        Enrollment.objects.active().filter(user=user, course=course).order_by("-expires_at").first()
    )
    if active and active.expires_at is None:
        return active
    starts_at = timezone.now()
    if active and active.expires_at:
        starts_at = active.expires_at
    return Enrollment.objects.create(
        user=user,
        course=course,
        starts_at=starts_at,
        expires_at=starts_at + timedelta(days=days) if days else None,
        source=Enrollment.Source.ORDER,
        order=order,
        note=f"سفارش {order.number}" if order else "",
    )


def mark_paid(order: Order, method: str, ref: str = "") -> bool:
    """Idempotently mark an order paid and grant access. Returns False if already paid.

    The passed instance is refreshed so callers see the new state.
    """
    changed = _mark_paid(order.pk, method, ref)
    order.refresh_from_db()
    if changed and order.payment_method != Order.Method.FREE:
        notify.order_paid(order)
    return changed


@transaction.atomic
def _mark_paid(order_pk: int, method: str, ref: str) -> bool:
    order = Order.objects.select_for_update().get(pk=order_pk)
    if order.is_paid:
        return False
    if order.status == Order.Status.CANCELLED:
        raise ShopError("این سفارش لغو شده است.")
    order.status = Order.Status.PAID
    order.payment_method = method
    order.payment_ref = ref or order.payment_ref
    order.paid_at = timezone.now()
    order.save()

    if order.course_id:
        grant_access(order.user, order.course, order.course.access_days, order)
    elif order.live_class_id:
        # Payment already received: register even if capacity filled up meanwhile.
        LiveRegistration.objects.get_or_create(
            user=order.user, live_class=order.live_class, defaults={"order": order}
        )
    else:
        bundle = order.bundle
        for course in bundle.courses.all():
            days = bundle.access_days if bundle.access_days else course.access_days
            grant_access(order.user, course, days, order)
    return True


def reject_receipt(order: Order, note: str = "") -> None:
    if order.status != Order.Status.AWAITING_REVIEW:
        return
    order.status = Order.Status.REJECTED
    order.admin_note = note or order.admin_note
    order.save(update_fields=["status", "admin_note", "updated_at"])
    notify.receipt_rejected(order)
