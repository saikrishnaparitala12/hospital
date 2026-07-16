from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from common.responses import success_response
from .serializers import PatientSerializer, AddressSerializer, EmergencyContactSerializer, MedicalIDSerializer
from . import services


class PatientProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        patient = services.get_or_create_patient(request.user)
        return success_response(PatientSerializer(patient).data)

    def patch(self, request):
        serializer = PatientSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        patient = services.update_patient(request.user, serializer.validated_data)
        return success_response(PatientSerializer(patient).data)


class AddressListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        patient = services.get_or_create_patient(request.user)
        return success_response(AddressSerializer(patient.addresses.all(), many=True).data)

    def post(self, request):
        serializer = AddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = services.add_address(request.user, serializer.validated_data)
        return success_response(AddressSerializer(address).data)


class AddressDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        serializer = AddressSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        address = services.update_address(request.user, pk, serializer.validated_data)
        return success_response(AddressSerializer(address).data)

    def delete(self, request, pk):
        services.delete_address(request.user, pk)
        return success_response(message="Address deleted.")


class EmergencyContactView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        patient = services.get_or_create_patient(request.user)
        return success_response(EmergencyContactSerializer(patient.emergency_contacts.all(), many=True).data)

    def post(self, request):
        serializer = EmergencyContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contact = services.add_emergency_contact(request.user, serializer.validated_data)
        return success_response(EmergencyContactSerializer(contact).data)

    def delete(self, request, pk):
        services.delete_emergency_contact(request.user, pk)
        return success_response(message="Emergency contact deleted.")


class MedicalIDView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        patient = services.get_or_create_patient(request.user)
        from .models import MedicalID
        obj, _ = MedicalID.objects.get_or_create(patient=patient)
        return success_response(MedicalIDSerializer(obj).data)

    def patch(self, request):
        serializer = MedicalIDSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = services.upsert_medical_id(request.user, serializer.validated_data)
        return success_response(MedicalIDSerializer(obj).data)
