from django.urls import path
from .views import (
    InsuranceSearchView,
    HospitalsByInsuranceView,
    NearbyHospitalsView,
    NearbyHospitalsByInsuranceView,
)

urlpatterns = [
    path("insurance/", InsuranceSearchView.as_view(), name="insurance-search"),
    path("insurance/<slug:slug>/hospitals/", HospitalsByInsuranceView.as_view(), name="hospitals-by-insurance"),
    path("hospitals/nearby/", NearbyHospitalsView.as_view(), name="nearby-hospitals"),
    path("insurance/<slug:slug>/hospitals/nearby/", NearbyHospitalsByInsuranceView.as_view(), name="nearby-hospitals-by-insurance"),
]
