from django.urls import path
from .views import (
    PatientProfileView,
    AddressListCreateView,
    AddressDetailView,
    EmergencyContactView,
    MedicalIDView,
)

urlpatterns = [
    path("patients/profile/", PatientProfileView.as_view(), name="patient-profile"),
    path("patients/addresses/", AddressListCreateView.as_view(), name="patient-addresses"),
    path("patients/addresses/<int:pk>/", AddressDetailView.as_view(), name="patient-address-detail"),
    path("patients/emergency-contacts/", EmergencyContactView.as_view(), name="patient-emergency-contacts"),
    path("patients/emergency-contacts/<int:pk>/", EmergencyContactView.as_view(), name="patient-emergency-contact-delete"),
    path("patients/medical-id/", MedicalIDView.as_view(), name="patient-medical-id"),
]
