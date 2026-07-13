from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, OTP, FCMToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["phone", "full_name", "role", "is_active", "is_phone_verified", "created_at"]
    list_filter = ["role", "is_active", "is_phone_verified"]
    search_fields = ["phone", "full_name", "email"]
    ordering = ["-created_at"]
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Personal", {"fields": ("full_name", "email")}),
        ("Permissions", {"fields": ("role", "is_active", "is_staff", "is_superuser", "is_phone_verified")}),
    )
    add_fieldsets = (
        (None, {"fields": ("phone", "full_name", "role", "password1", "password2")}),
    )


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ["user", "code", "is_used", "expires_at", "created_at"]
    list_filter = ["is_used"]
    search_fields = ["user__phone"]


@admin.register(FCMToken)
class FCMTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "device_type", "created_at"]
    search_fields = ["user__phone"]
