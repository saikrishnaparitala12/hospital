from django.contrib import admin
from .models import Department, Counter


class CounterInline(admin.TabularInline):
    model = Counter
    extra = 0


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "average_service_time", "reminder_threshold_tokens", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    inlines = [CounterInline]
