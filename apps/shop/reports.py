"""Sales report for the admin panel (Jalali months)."""

from collections import OrderedDict
from datetime import timedelta

import jdatetime
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Enrollment

from .models import Order

MONTHS = 12


def _totals(qs):
    data = qs.aggregate(revenue=Sum("total"), count=Count("id"))
    return {"revenue": data["revenue"] or 0, "count": data["count"]}


def _jalali_month(dt):
    j = jdatetime.datetime.fromgregorian(datetime=timezone.localtime(dt))
    return j.year, j.month


def _monthly(paid):
    """Revenue for the last MONTHS Jalali months (oldest first, empty months included)."""
    today = jdatetime.date.fromgregorian(date=timezone.localdate())
    months = OrderedDict()
    year, month = today.year, today.month
    for _ in range(MONTHS):
        months[(year, month)] = {"label": f"{year}/{month:02d}", "revenue": 0, "count": 0}
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    start = timezone.now() - timedelta(days=31 * MONTHS + 31)
    for paid_at, total in paid.filter(paid_at__gte=start).values_list("paid_at", "total"):
        key = _jalali_month(paid_at)
        if key in months:
            months[key]["revenue"] += total
            months[key]["count"] += 1
    return list(reversed(months.values()))


def build_report():
    now = timezone.now()
    paid = Order.objects.filter(status=Order.Status.PAID)
    today = jdatetime.date.fromgregorian(date=timezone.localdate())
    month_start = timezone.make_aware(jdatetime.datetime(today.year, today.month, 1).togregorian())
    by_type = {
        "دوره": _totals(paid.filter(course__isnull=False)),
        "پکیج": _totals(paid.filter(bundle__isnull=False)),
        "کلاس زنده": _totals(paid.filter(live_class__isnull=False)),
    }
    return {
        "today": _totals(paid.filter(paid_at__date=timezone.localdate())),
        "this_month": _totals(paid.filter(paid_at__gte=month_start)),
        "last_30": _totals(paid.filter(paid_at__gte=now - timedelta(days=30))),
        "all_time": _totals(paid),
        "monthly": _monthly(paid),
        "by_type": by_type,
        "top_products": paid.values("title")
        .annotate(revenue=Sum("total"), count=Count("id"))
        .order_by("-revenue")[:10],
        "methods": [
            {"label": Order.Method(row["payment_method"]).label, **row}
            for row in paid.exclude(payment_method="")
            .values("payment_method")
            .annotate(revenue=Sum("total"), count=Count("id"))
            .order_by("-revenue")
        ],
        "discounts": paid.exclude(discount_code=None)
        .values("discount_code__code")
        .annotate(count=Count("id"), discount=Sum("discount_amount"), revenue=Sum("total"))
        .order_by("-count"),
        "pending_review": Order.objects.filter(status=Order.Status.AWAITING_REVIEW).count(),
        "users": User.objects.filter(is_staff=False).count(),
        "active_students": Enrollment.objects.active()
        .filter(Q(user__is_staff=False))
        .values("user")
        .distinct()
        .count(),
    }


@staff_member_required
def sales_report(request):
    context = {**admin.site.each_context(request), "title": "گزارش فروش", **build_report()}
    return render(request, "admin/shop/report.html", context)
