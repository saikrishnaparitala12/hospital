from django.contrib import admin
from .models import Department, Counter, HospitalConfig


class CounterInline(admin.TabularInline):
    model = Counter
    extra = 0


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "average_service_time", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    inlines = [CounterInline]


@admin.register(HospitalConfig)
class HospitalConfigAdmin(admin.ModelAdmin):
    list_display = ["key", "value", "description"]
    search_fields = ["key"]
