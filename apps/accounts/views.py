from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from apps.core.utils import client_ip

from . import otp
from .forms import CodeForm, PhoneForm, ProfileForm
from .models import User
from .sms import SMSError

SESSION_PHONE = "otp_phone"
SESSION_NEXT = "otp_next"


def _safe_next(request, url):
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return reverse("catalog:my_courses")


def login_phone(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request, request.GET.get("next")))

    form = PhoneForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        phone = form.cleaned_data["phone"]
        request.session[SESSION_NEXT] = request.POST.get("next") or request.GET.get("next")
        try:
            otp.request_code(phone, client_ip(request))
        except otp.OTPError as exc:
            if otp.seconds_until_resend(phone):
                # A code was already sent recently; let the user enter it.
                request.session[SESSION_PHONE] = phone
                messages.info(request, str(exc))
                return redirect("accounts:verify")
            form.add_error(None, str(exc))
        except SMSError as exc:
            form.add_error(None, str(exc))
        else:
            request.session[SESSION_PHONE] = phone
            return redirect("accounts:verify")

    return render(
        request, "accounts/login.html", {"form": form, "next": request.GET.get("next", "")}
    )


def login_verify(request):
    phone = request.session.get(SESSION_PHONE)
    if not phone:
        return redirect("accounts:login")

    form = CodeForm()
    if request.method == "POST" and request.POST.get("action") == "resend":
        try:
            otp.request_code(phone, client_ip(request))
            messages.success(request, "کد جدید ارسال شد.")
        except (otp.OTPError, SMSError) as exc:
            messages.error(request, str(exc))
        return redirect("accounts:verify")

    if request.method == "POST":
        form = CodeForm(request.POST)
        if form.is_valid():
            try:
                otp.verify_code(phone, form.cleaned_data["code"])
            except otp.OTPError as exc:
                form.add_error("code", str(exc))
            else:
                user, _ = User.objects.get_or_create(phone=phone)
                if not user.is_active:
                    form.add_error(None, "حساب کاربری شما غیرفعال است.")
                else:
                    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                    next_url = _safe_next(request, request.session.pop(SESSION_NEXT, None))
                    request.session.pop(SESSION_PHONE, None)
                    if not user.first_name:
                        return redirect(
                            f"{reverse('accounts:profile')}?{urlencode({'next': next_url})}"
                        )
                    return redirect(next_url)

    return render(
        request,
        "accounts/verify.html",
        {"form": form, "phone": phone, "wait_seconds": otp.seconds_until_resend(phone)},
    )


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "مشخصات شما ذخیره شد.")
        return redirect(_safe_next(request, request.GET.get("next")))
    return render(request, "accounts/profile.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("core:home")
