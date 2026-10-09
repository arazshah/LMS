from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


class UserCreationForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("phone", "first_name", "last_name")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    ordering = ("-date_joined",)
    list_display = ("phone", "first_name", "last_name", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff")
    search_fields = ("phone", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("مشخصات", {"fields": ("first_name", "last_name")}),
        ("دسترسی‌ها", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("تاریخ‌ها", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"fields": ("phone", "first_name", "last_name")}),)
    filter_horizontal = ()
