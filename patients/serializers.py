from rest_framework import serializers
from .models import Patient, Address, EmergencyContact, MedicalID


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ["id", "line1", "line2", "city", "state", "pincode", "is_default"]


class EmergencyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyContact
        fields = ["id", "name", "relationship", "phone"]


class MedicalIDSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalID
        fields = ["id", "allergies", "chronic_conditions", "current_medications", "notes"]


class PatientSerializer(serializers.ModelSerializer):
    age = serializers.ReadOnlyField()
    addresses = AddressSerializer(many=True, read_only=True)
    emergency_contacts = EmergencyContactSerializer(many=True, read_only=True)
    medical_id = MedicalIDSerializer(read_only=True)

    class Meta:
        model = Patient
        fields = [
            "id", "date_of_birth", "age", "gender", "blood_group",
            "profile_photo", "addresses", "emergency_contacts", "medical_id",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
