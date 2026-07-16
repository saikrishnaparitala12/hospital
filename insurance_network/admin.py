from django.contrib import admin
from .models import InsuranceCompany, Hospital, InsuranceHospitalNetwork, ScrapeLog


@admin.register(InsuranceCompany)
class InsuranceCompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "last_scraped_at"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "state", "pincode", "latitude", "longitude"]
    search_fields = ["name", "city", "pincode"]
    list_filter = ["state", "city"]


@admin.register(InsuranceHospitalNetwork)
class InsuranceHospitalNetworkAdmin(admin.ModelAdmin):
    list_display = ["insurance", "hospital", "is_active"]
    list_filter = ["insurance", "is_active"]
    search_fields = ["hospital__name"]


@admin.register(ScrapeLog)
class ScrapeLogAdmin(admin.ModelAdmin):
    list_display = ["insurance", "status", "hospitals_found", "started_at", "finished_at"]
    list_filter = ["status", "insurance"]
    readonly_fields = ["started_at", "finished_at", "error_message"]
