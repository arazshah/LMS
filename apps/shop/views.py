import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.catalog.models import Course
from apps.live.models import LiveClass
from apps.siteconfig.models import SiteSettings

from . import bale, services
from .forms import ReceiptForm
from .invoice import render_invoice_pdf
from .models import Bundle, Order

logger = logging.getLogger(__name__)


def bundle_list(request):
    bundles = Bundle.objects.filter(is_published=True).prefetch_related("courses")
    return render(request, "shop/bundle_list.html", {"bundles": bundles})


def bundle_detail(request, slug):
    bundle = get_object_or_404(Bundle.objects.filter(is_published=True), slug=slug)
    return render(
        request,
        "shop/bundle_detail.html",
        {"bundle": bundle, "courses": bundle.courses.filter(is_published=True)},
    )


def _product(kind, slug):
    model = {"course": Course, "bundle": Bundle, "live": LiveClass}.get(kind)
    if model is None:
        raise Http404
    return get_object_or_404(model.objects.filter(is_published=True), slug=slug)


@login_required
def checkout(request, kind, slug):
    product = _product(kind, slug)
    code = (request.POST.get("code") or "").strip()
    error = None
    q = None
    try:
        services.check_can_buy(request.user, product)
        q = services.quote(request.user, product, code)
    except services.ShopError as exc:
        error = str(exc)
        if code:
            # Bad code: show the price without it so the buyer can still continue.
            q = services.quote(request.user, product)

    if request.method == "POST" and request.POST.get("action") == "pay" and q and not error:
        order = services.create_order(request.user, product, code)
        if order.is_paid:
            messages.success(request, "سفارش شما ثبت شد و دسترسی فعال است.")
            return redirect(product.get_absolute_url() if kind == "live" else "catalog:my_courses")
        return redirect(order)

    return render(
        request,
        "shop/checkout.html",
        {"product": product, "kind": kind, "quote": q, "code": code, "error": error},
    )


def _own_order(request, number):
    order = get_object_or_404(Order, number=number)
    if order.user_id != request.user.id and not request.user.is_staff:
        raise Http404
    return order


@login_required
def order_pay(request, number):
    order = _own_order(request, number)
    form = ReceiptForm()
    if request.method == "POST" and order.can_pay:
        form = ReceiptForm(request.POST, request.FILES)
        if form.is_valid():
            order.receipt = form.cleaned_data["receipt"]
            order.receipt_ref = form.cleaned_data["receipt_ref"]
            order.mark_receipt_submitted()
            order.save()
            messages.success(request, "رسید شما ثبت شد؛ پس از بررسی، دسترسی فعال می‌شود.")
            return redirect(order)
    config = SiteSettings.load()
    return render(
        request,
        "shop/order_pay.html",
        {
            "order": order,
            "form": form,
            "bale_link": bale.deep_link(order) if config.bale_configured else None,
        },
    )


@login_required
def order_status(request, number):
    """Polled by the payment page (htmx) to notice a Bale payment."""
    order = _own_order(request, number)
    if order.is_paid:
        response = HttpResponse()
        response["HX-Redirect"] = order.get_absolute_url()
        return response
    return HttpResponse(status=204)


@login_required
def order_list(request):
    orders = request.user.orders.select_related("course", "bundle", "live_class")
    return render(request, "shop/order_list.html", {"orders": orders})


@login_required
def order_invoice(request, number):
    order = _own_order(request, number)
    if not order.is_paid:
        raise Http404
    response = HttpResponse(render_invoice_pdf(order), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="invoice-{order.number}.pdf"'
    return response


@login_required
def order_receipt(request, number):
    if not request.user.is_staff:
        raise Http404
    order = get_object_or_404(Order, number=number)
    if not order.receipt:
        raise Http404
    return FileResponse(order.receipt.open("rb"))


@csrf_exempt
@require_POST
def bale_webhook(request, secret):
    if secret != SiteSettings.load().bale_webhook_secret:
        raise Http404
    try:
        update = json.loads(request.body)
    except ValueError:
        return JsonResponse({"ok": False}, status=400)
    bale.handle_update(update)
    return JsonResponse({"ok": True})
