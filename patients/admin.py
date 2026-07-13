from django.contrib import admin
from .models import Patient, Address, EmergencyContact, MedicalID


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0


class EmergencyContactInline(admin.TabularInline):
    model = EmergencyContact
    extra = 0


class MedicalIDInline(admin.StackedInline):
    model = MedicalID
    extra = 0


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ["user", "gender", "blood_group", "date_of_birth", "created_at"]
    search_fields = ["user__phone", "user__full_name"]
    list_filter = ["gender", "blood_group"]
    inlines = [AddressInline, EmergencyContactInline, MedicalIDInline]
