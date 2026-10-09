import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Course, _unique_slug, cover_upload_to


def receipt_upload_to(instance, filename):
    return f"protected/receipts/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class Bundle(models.Model):
    """A package of courses sold at one price."""

    title = models.CharField("عنوان", max_length=200)
    slug = models.SlugField("نامک", max_length=100, unique=True, allow_unicode=True, blank=True)
    summary = models.CharField("خلاصه", max_length=300, blank=True)
    description = models.TextField("توضیحات", blank=True)
    cover = models.ImageField("تصویر جلد", upload_to=cover_upload_to, blank=True)
    courses = models.ManyToManyField(Course, related_name="bundles", verbose_name="دوره‌ها")
    price = models.PositiveIntegerField("قیمت (تومان)")
    access_days = models.PositiveIntegerField(
        "مدت دسترسی (روز)",
        null=True,
        blank=True,
        help_text="خالی = برای هر دوره، مدت دسترسی خود آن دوره",
    )
    is_published = models.BooleanField("منتشر شده", default=False)
    order = models.PositiveIntegerField("ترتیب", default=0)
    created_at = models.DateTimeField("ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "پکیج"
        verbose_name_plural = "پکیج‌ها"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("shop:bundle_detail", args=[self.slug])

    @property
    def original_price(self):
        return self.courses.aggregate(total=Sum("price"))["total"] or 0


class DiscountCode(models.Model):
    class Kind(models.TextChoices):
        PERCENT = "percent", "درصدی"
        FIXED = "fixed", "مبلغ ثابت (تومان)"

    code = models.CharField("کد", max_length=40, unique=True, help_text="حروف انگلیسی و عدد")
    kind = models.CharField("نوع", max_length=10, choices=Kind, default=Kind.PERCENT)
    value = models.PositiveIntegerField("مقدار", help_text="درصد (۱ تا ۱۰۰) یا مبلغ به تومان")
    max_discount = models.PositiveIntegerField(
        "سقف تخفیف (تومان)", null=True, blank=True, help_text="فقط برای کد درصدی؛ خالی = بدون سقف"
    )
    min_amount = models.PositiveIntegerField("حداقل مبلغ خرید (تومان)", default=0)
    valid_from = models.DateTimeField("شروع اعتبار", null=True, blank=True)
    valid_until = models.DateTimeField("پایان اعتبار", null=True, blank=True)
    max_uses = models.PositiveIntegerField(
        "حداکثر تعداد استفاده", null=True, blank=True, help_text="خالی = نامحدود"
    )
    one_per_user = models.BooleanField("هر کاربر فقط یک بار", default=True)
    courses = models.ManyToManyField(
        Course,
        blank=True,
        related_name="discount_codes",
        verbose_name="فقط برای این دوره‌ها",
        help_text="اگر هیچ دوره و پکیجی انتخاب نشود، کد برای همه معتبر است.",
    )
    bundles = models.ManyToManyField(
        Bundle, blank=True, related_name="discount_codes", verbose_name="فقط برای این پکیج‌ها"
    )
    live_classes = models.ManyToManyField(
        "live.LiveClass",
        blank=True,
        related_name="discount_codes",
        verbose_name="فقط برای این کلاس‌های زنده",
    )
    is_active = models.BooleanField("فعال", default=True)
    created_at = models.DateTimeField("ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "کد تخفیف"
        verbose_name_plural = "کدهای تخفیف"
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def used_count(self):
        return self.orders.filter(status=Order.Status.PAID).count()

    def discount_for(self, amount: int) -> int:
        if self.kind == self.Kind.PERCENT:
            discount = amount * min(self.value, 100) // 100
            if self.max_discount is not None:
                discount = min(discount, self.max_discount)
        else:
            discount = self.value
        return min(discount, amount)


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار پرداخت"
        AWAITING_REVIEW = "review", "در انتظار تأیید رسید"
        PAID = "paid", "پرداخت شده"
        REJECTED = "rejected", "رسید تأیید نشد"
        CANCELLED = "cancelled", "لغو شده"

    class Method(models.TextChoices):
        BALE = "bale", "پرداخت در بله"
        CARD = "card", "کارت‌به‌کارت"
        FREE = "free", "رایگان (کد تخفیف)"
        MANUAL = "manual", "ثبت دستی ادمین"

    number = models.CharField("شماره سفارش", max_length=20, unique=True, blank=True)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="کاربر",
    )
    course = models.ForeignKey(
        Course, on_delete=models.PROTECT, null=True, blank=True, related_name="orders",
        verbose_name="دوره",
    )  # fmt: skip
    bundle = models.ForeignKey(
        Bundle, on_delete=models.PROTECT, null=True, blank=True, related_name="orders",
        verbose_name="پکیج",
    )  # fmt: skip
    live_class = models.ForeignKey(
        "live.LiveClass", on_delete=models.PROTECT, null=True, blank=True, related_name="orders",
        verbose_name="کلاس زنده",
    )  # fmt: skip
    title = models.CharField("عنوان", max_length=200)
    amount = models.PositiveIntegerField("مبلغ (تومان)")
    discount_code = models.ForeignKey(
        DiscountCode, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders",
        verbose_name="کد تخفیف",
    )  # fmt: skip
    discount_amount = models.PositiveIntegerField("تخفیف (تومان)", default=0)
    total = models.PositiveIntegerField("مبلغ قابل پرداخت (تومان)")
    status = models.CharField("وضعیت", max_length=20, choices=Status, default=Status.PENDING)
    payment_method = models.CharField("روش پرداخت", max_length=20, choices=Method, blank=True)
    payment_ref = models.CharField("شناسه پرداخت", max_length=200, blank=True)
    receipt = models.ImageField("تصویر رسید", upload_to=receipt_upload_to, blank=True)
    receipt_ref = models.CharField("شماره پیگیری / توضیح خریدار", max_length=200, blank=True)
    receipt_submitted_at = models.DateTimeField("زمان ارسال رسید", null=True, blank=True)
    bale_chat_id = models.CharField("شناسه چت بله", max_length=50, blank=True)
    admin_note = models.CharField("یادداشت ادمین", max_length=500, blank=True)
    paid_at = models.DateTimeField("زمان پرداخت", null=True, blank=True)
    created_at = models.DateTimeField("ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("به‌روزرسانی", auto_now=True)

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    course__isnull=False, bundle__isnull=True, live_class__isnull=True
                )
                | models.Q(course__isnull=True, bundle__isnull=False, live_class__isnull=True)
                | models.Q(course__isnull=True, bundle__isnull=True, live_class__isnull=False),
                name="order_has_exactly_one_product",
            )
        ]

    def __str__(self):
        return f"سفارش {self.number}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = str(1000 + self.pk)
            super().save(update_fields=["number"])

    def get_absolute_url(self):
        return reverse("shop:order_pay", args=[self.number])

    @property
    def product(self):
        return self.course or self.bundle or self.live_class

    @property
    def product_kind_label(self):
        if self.bundle_id:
            return "پکیج"
        if self.live_class_id:
            return "کلاس زنده"
        return "دوره"

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

    @property
    def can_pay(self):
        return self.status in (self.Status.PENDING, self.Status.REJECTED)

    @property
    def amount_rial(self):
        return self.total * 10

    def mark_receipt_submitted(self):
        self.status = self.Status.AWAITING_REVIEW
        self.payment_method = self.Method.CARD
        self.receipt_submitted_at = timezone.now()
