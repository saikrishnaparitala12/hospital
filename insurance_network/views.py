import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from .models import InsuranceCompany
from .serializers import InsuranceCompanySerializer, HospitalSerializer, NearbyHospitalSerializer
from .services import InsuranceNetworkService
from .tasks import sync_insurance_network

logger = logging.getLogger(__name__)


def _trigger_sync_if_stale(insurance: InsuranceCompany):
    """Fire-and-forget background sync if data is stale. Never blocks the request."""
    if InsuranceNetworkService.is_data_stale(insurance):
        sync_insurance_network.delay(insurance.slug)
        logger.info("Triggered background sync for %s", insurance.slug)


class InsuranceSearchView(APIView):
    """GET /api/v1/insurance/?q=star"""
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.query_params.get("q", "")
        insurances = InsuranceNetworkService.search_insurance(query)
        return Response(InsuranceCompanySerializer(insurances, many=True).data)


class HospitalsByInsuranceView(APIView):
    """GET /api/v1/insurance/<slug>/hospitals/"""
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            insurance = InsuranceCompany.objects.get(slug=slug, is_active=True)
        except InsuranceCompany.DoesNotExist:
            return Response({"detail": "Insurance not found."}, status=status.HTTP_404_NOT_FOUND)

        _trigger_sync_if_stale(insurance)

        hospitals = InsuranceNetworkService.hospitals_by_insurance(slug)
        return Response(HospitalSerializer(hospitals, many=True).data)


class NearbyHospitalsView(APIView):
    """GET /api/v1/hospitals/nearby/?lat=12.9&lon=77.5&radius=10"""
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            lat = float(request.query_params["lat"])
            lon = float(request.query_params["lon"])
            radius = float(request.query_params.get("radius", 10))
        except (KeyError, ValueError):
            return Response({"detail": "lat and lon are required numeric parameters."}, status=status.HTTP_400_BAD_REQUEST)

        hospitals = InsuranceNetworkService.nearby_hospitals(lat, lon, radius)
        return Response(NearbyHospitalSerializer(hospitals, many=True).data)


class NearbyHospitalsByInsuranceView(APIView):
    """GET /api/v1/insurance/<slug>/hospitals/nearby/?lat=12.9&lon=77.5&radius=10"""
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            insurance = InsuranceCompany.objects.get(slug=slug, is_active=True)
        except InsuranceCompany.DoesNotExist:
            return Response({"detail": "Insurance not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            lat = float(request.query_params["lat"])
            lon = float(request.query_params["lon"])
            radius = float(request.query_params.get("radius", 10))
        except (KeyError, ValueError):
            return Response({"detail": "lat and lon are required numeric parameters."}, status=status.HTTP_400_BAD_REQUEST)

        _trigger_sync_if_stale(insurance)

        hospitals = InsuranceNetworkService.nearby_hospitals_by_insurance(lat, lon, slug, radius)
        return Response(NearbyHospitalSerializer(hospitals, many=True).data)
