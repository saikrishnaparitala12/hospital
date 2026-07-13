from django.contrib import admin
from .models import NotificationLog, ReminderLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ["user", "notification_type", "title", "is_read", "sent_at"]
    list_filter = ["notification_type", "is_read"]
    search_fields = ["user__phone", "title"]
    ordering = ["-sent_at"]


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ["token", "scheduled_at", "sent_at", "is_sent"]
    list_filter = ["is_sent"]
