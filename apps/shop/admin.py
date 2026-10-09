from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from apps.core.templatetags.fa import jdate

from . import services
from .models import Bundle, DiscountCode, Order


@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ("title", "price", "original_price_display", "access_days", "is_published")
    list_editable = ("is_published",)
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("courses",)

    @admin.display(description="مجموع قیمت دوره‌ها")
    def original_price_display(self, obj):
        return obj.original_price


@admin.register(DiscountCode)
class DiscountCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "kind", "value", "valid_until", "uses", "is_active")
    list_filter = ("is_active", "kind")
    search_fields = ("code",)
    filter_horizontal = ("courses", "bundles")
    fieldsets = (
        (None, {"fields": ("code", "kind", "value", "max_discount", "is_active")}),
        (
            "محدودیت‌ها",
            {"fields": ("min_amount", "valid_from", "valid_until", "max_uses", "one_per_user")},
        ),  # fmt: skip
        ("محصولات مجاز", {"fields": ("courses", "bundles")}),
    )

    @admin.display(description="تعداد استفاده")
    def uses(self, obj):
        return f"{obj.used_count} / {obj.max_uses or '∞'}"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number", "user", "title", "total", "payment_method", "status_badge", "created_at",
    )  # fmt: skip
    list_filter = ("status", "payment_method", "created_at")
    search_fields = ("number", "user__phone", "user__first_name", "user__last_name", "title")
    list_select_related = ("user",)
    date_hierarchy = "created_at"
    actions = ["approve", "reject"]
    readonly_fields = (
        "number", "user", "title", "course", "bundle", "amount", "discount_code",
        "discount_amount", "total", "status", "payment_method", "payment_ref",
        "receipt_preview", "receipt_ref", "receipt_submitted_at", "bale_chat_id", "paid_at",
        "created_at", "access_list",
    )  # fmt: skip
    fieldsets = (
        (None, {"fields": ("number", "user", "title", "course", "bundle", "status")}),
        ("مبلغ", {"fields": ("amount", "discount_code", "discount_amount", "total")}),
        (
            "پرداخت",
            {
                "fields": (
                    "payment_method",
                    "payment_ref",
                    "receipt_preview",
                    "receipt_ref",
                    "receipt_submitted_at",
                    "bale_chat_id",
                    "paid_at",
                )
            },
        ),  # fmt: skip
        ("دسترسی‌ها و یادداشت", {"fields": ("access_list", "admin_note", "created_at")}),
    )

    change_form_template = "admin/shop/order/change_form.html"

    def has_add_permission(self, request):
        return False

    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [
            path("<int:pk>/approve/", wrap(self.approve_view), name="shop_order_approve"),
            path("<int:pk>/reject/", wrap(self.reject_view), name="shop_order_reject"),
            *super().get_urls(),
        ]

    def _back(self, order):
        return redirect(reverse("admin:shop_order_change", args=[order.pk]))

    def approve_view(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        if request.method == "POST":
            try:
                services.mark_paid(order, order.payment_method or Order.Method.MANUAL)
                self.message_user(request, "پرداخت تأیید و دسترسی فعال شد.")
            except services.ShopError as exc:
                self.message_user(request, str(exc), messages.ERROR)
        return self._back(order)

    def reject_view(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        if request.method == "POST":
            services.reject_receipt(order, request.POST.get("note", ""))
            self.message_user(request, "رسید رد شد؛ خریدار می‌تواند رسید جدید بفرستد.")
        return self._back(order)

    @admin.display(description="وضعیت")
    def status_badge(self, obj):
        colors = {
            Order.Status.PAID: "#047857",
            Order.Status.AWAITING_REVIEW: "#b45309",
            Order.Status.REJECTED: "#b91c1c",
        }
        return format_html(
            '<b style="color:{}">{}</b>',
            colors.get(obj.status, "#475569"),
            obj.get_status_display(),
        )

    @admin.display(description="تصویر رسید")
    def receipt_preview(self, obj):
        if not obj.receipt:
            return "—"
        url = reverse("shop:order_receipt", args=[obj.number])
        return format_html(
            '<a href="{0}" target="_blank"><img src="{0}" style="max-width:320px;'
            'max-height:420px;border:1px solid #ddd"></a>',
            url,
        )

    @admin.display(description="دسترسی‌های ایجادشده")
    def access_list(self, obj):
        items = obj.enrollments.select_related("course")
        if not items:
            return "—"
        return format_html_join(
            format_html("<br>"),
            "{} — تا {}",
            ((e.course, jdate(e.expires_at) if e.expires_at else "دائمی") for e in items),
        )

    @admin.action(description="✅ تأیید پرداخت و فعال‌سازی دسترسی")
    def approve(self, request, queryset):
        count = 0
        for order in queryset:
            try:
                method = order.payment_method or Order.Method.MANUAL
                if services.mark_paid(order, method):
                    count += 1
            except services.ShopError as exc:
                self.message_user(request, f"{order}: {exc}", messages.ERROR)
        self.message_user(request, f"{count} سفارش تأیید و دسترسی آن فعال شد.")

    @admin.action(description="❌ رد رسید (خریدار می‌تواند رسید جدید بفرستد)")
    def reject(self, request, queryset):
        for order in queryset:
            services.reject_receipt(order)
        self.message_user(request, "رسیدهای انتخاب‌شده رد شدند.")
