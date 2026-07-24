import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import InsuranceCompanySerializer, HospitalSerializer, NearbyHospitalSerializer
from .services import (
    HospitalService,
    InsuranceProviderNotSupported,
    InsuranceService,
    SyncService,
)

logger = logging.getLogger(__name__)


def _provider_not_supported_response(identifier: str, exc: InsuranceProviderNotSupported):
    return Response(
        {
            "success": False,
            "status": "provider_not_supported",
            "message": "This insurance provider is not available for network hospital lookup yet.",
            "query": identifier,
            "suggestions": exc.suggestions,
            "hospitals": [],
        },
        status=status.HTTP_404_NOT_FOUND,
    )


def _queue_sync_response(insurance, queued: bool):
    http_status = status.HTTP_202_ACCEPTED if queued else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(
        {
            "success": queued,
            "syncing": queued,
            "status": "sync_queued" if queued else "sync_queue_failed",
            "message": (
                "Hospital network data is being synchronized. Please try again in a few minutes."
                if queued
                else "Hospital network data is not available and background sync could not be queued."
            ),
            "insurance": InsuranceCompanySerializer(insurance).data,
            "count": 0,
            "hospitals": [],
        },
        status=http_status,
    )


def _hospital_list_response(insurance, hospitals, refresh_queued: bool = False):
    return Response(
        {
            "success": True,
            "syncing": False,
            "status": "served_from_db",
            "message": "Hospital network data served from the database.",
            "insurance": InsuranceCompanySerializer(insurance).data,
            "refresh_queued": refresh_queued,
            "count": hospitals.count(),
            "hospitals": HospitalSerializer(hospitals, many=True).data,
        }
    )


class InsuranceSearchView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.query_params.get("q", "")
        insurances = InsuranceService.search(query)
        return Response(
            {
                "success": True,
                "status": "ok",
                "query": query,
                "count": len(insurances),
                "results": InsuranceCompanySerializer(insurances, many=True).data,
            }
        )


class HospitalsByInsuranceView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            insurance, _ = InsuranceService.get_or_create_supported(slug)
        except InsuranceProviderNotSupported as exc:
            return _provider_not_supported_response(slug, exc)

        has_data = SyncService.has_hospitals(insurance)
        if not has_data:
            queued = SyncService.trigger_background_sync(insurance)
            return _queue_sync_response(insurance, queued)

        refresh_queued = False
        if SyncService.is_stale(insurance):
            refresh_queued = SyncService.trigger_background_sync(insurance)
            logger.info("Stale insurance data for %s, refresh_queued=%s", insurance.slug, refresh_queued)

        hospitals = HospitalService.by_insurance(insurance.slug)
        return _hospital_list_response(insurance, hospitals, refresh_queued=refresh_queued)


class NearbyHospitalsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            lat = float(request.query_params["lat"])
            lon = float(request.query_params["lon"])
            radius = float(request.query_params.get("radius", 10))
        except (KeyError, ValueError):
            return Response(
                {"detail": "lat and lon are required numeric parameters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hospitals = HospitalService.nearby(lat, lon, radius)
        return Response(
            {
                "success": True,
                "status": "ok",
                "count": len(hospitals),
                "hospitals": NearbyHospitalSerializer(hospitals, many=True).data,
            }
        )


class NearbyHospitalsByInsuranceView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            insurance, _ = InsuranceService.get_or_create_supported(slug)
        except InsuranceProviderNotSupported as exc:
            return _provider_not_supported_response(slug, exc)

        try:
            lat = float(request.query_params["lat"])
            lon = float(request.query_params["lon"])
            radius = float(request.query_params.get("radius", 10))
        except (KeyError, ValueError):
            return Response(
                {"detail": "lat and lon are required numeric parameters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        has_data = SyncService.has_hospitals(insurance)
        if not has_data:
            queued = SyncService.trigger_background_sync(insurance)
            return _queue_sync_response(insurance, queued)

        if SyncService.is_stale(insurance):
            SyncService.trigger_background_sync(insurance)

        hospitals = HospitalService.nearby_by_insurance(lat, lon, insurance.slug, radius)
        return Response(
            {
                "success": True,
                "syncing": False,
                "status": "served_from_db",
                "insurance": InsuranceCompanySerializer(insurance).data,
                "count": len(hospitals),
                "hospitals": NearbyHospitalSerializer(hospitals, many=True).data,
            }
        )
