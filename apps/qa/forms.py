from django import forms

from .models import Question


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ("body",)
        labels = {"body": "سوال شما"}
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 3,
                    "maxlength": 3000,
                    "placeholder": "سوالتان درباره این جلسه را بنویسید...",
                    "class": "w-full rounded-lg border border-slate-300 px-4 py-3 "
                    "focus:border-emerald-600 focus:outline-none",
                }
            )
        }
