from django import forms

_INPUT = (
    "w-full rounded-lg border border-slate-300 px-4 py-3 "
    "focus:border-emerald-600 focus:outline-none"
)
MAX_RECEIPT_SIZE = 5 * 1024 * 1024


class ReceiptForm(forms.Form):
    receipt = forms.ImageField(
        label="تصویر رسید", widget=forms.ClearableFileInput(attrs={"accept": "image/*"})
    )
    receipt_ref = forms.CharField(
        label="شماره پیگیری یا ۴ رقم آخر کارت (اختیاری)",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"class": _INPUT}),
    )

    def clean_receipt(self):
        receipt = self.cleaned_data["receipt"]
        if receipt.size > MAX_RECEIPT_SIZE:
            raise forms.ValidationError("حجم تصویر باید کمتر از ۵ مگابایت باشد.")
        return receipt
