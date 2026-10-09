from django import forms
from django.core.exceptions import ValidationError

from .models import User
from .phone import normalize_phone

_INPUT = (
    "w-full rounded-lg border border-slate-300 px-4 py-3 "
    "focus:border-emerald-600 focus:outline-none"
)


class PhoneForm(forms.Form):
    phone = forms.CharField(
        label="شماره موبایل",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": _INPUT + " text-left",
                "dir": "ltr",
                "inputmode": "tel",
                "autocomplete": "tel",
                "placeholder": "09xxxxxxxxx",
                "autofocus": True,
            }
        ),
    )

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])


class CodeForm(forms.Form):
    code = forms.CharField(
        label="کد تأیید",
        max_length=10,
        widget=forms.TextInput(
            attrs={
                "class": _INPUT + " text-center tracking-[0.5em]",
                "dir": "ltr",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "autofocus": True,
            }
        ),
    )

    def clean_code(self):
        code = self.cleaned_data["code"].translate(
            str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        )
        if not code.strip().isdigit():
            raise ValidationError("کد باید فقط شامل عدد باشد.")
        return code.strip()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": _INPUT}),
            "last_name": forms.TextInput(attrs={"class": _INPUT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True
