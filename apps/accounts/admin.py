from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group

from .models import OTPCode, User


class UserCreationForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("phone", "first_name", "last_name")


# Single-admin site: permission groups are not needed.
admin.site.unregister(Group)


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


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ("phone", "created_at", "expires_at", "attempts", "used")
    search_fields = ("phone",)
    readonly_fields = ("phone", "code_hash", "created_at", "expires_at", "attempts", "used")

    def has_add_permission(self, request):
        return False
