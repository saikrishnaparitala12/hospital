from django.contrib import admin
from .models import PatientToken, DailyTokenSequence


@admin.register(PatientToken)
class PatientTokenAdmin(admin.ModelAdmin):
    list_display = ["token_number", "patient", "department", "date", "status", "is_emergency", "estimated_time"]
    list_filter = ["status", "is_emergency", "department", "date"]
    search_fields = ["patient__phone", "patient__full_name"]
    ordering = ["-date", "-is_emergency", "token_number"]
    actions = ["mark_completed", "mark_missed"]

    @admin.action(description="Mark selected tokens as completed")
    def mark_completed(self, request, queryset):
        from django.utils import timezone
        from common.choices import TokenStatus
        queryset.update(status=TokenStatus.COMPLETED, completed_at=timezone.now())

    @admin.action(description="Mark selected tokens as missed")
    def mark_missed(self, request, queryset):
        from common.choices import TokenStatus
        queryset.update(status=TokenStatus.MISSED)


@admin.register(DailyTokenSequence)
class DailyTokenSequenceAdmin(admin.ModelAdmin):
    list_display = ["department", "date", "last_number"]
    list_filter = ["department", "date"]
