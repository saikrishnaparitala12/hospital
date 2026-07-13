from rest_framework import serializers
from .models import PatientToken


class TokenSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    counter_name = serializers.CharField(source="counter.name", read_only=True)
    patient_phone = serializers.CharField(source="patient.phone", read_only=True)

    class Meta:
        model = PatientToken
        fields = [
            "id", "token_number", "date", "status",
            "department", "department_name",
            "counter", "counter_name",
            "patient_phone", "estimated_time",
            "checked_in_at", "completed_at", "notes",
            "created_at",
        ]
        read_only_fields = ["id", "token_number", "date", "status", "estimated_time", "created_at"]


class IssueTokenSerializer(serializers.Serializer):
    department_id = serializers.IntegerField()


class QueueSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    patient_phone = serializers.CharField(source="patient.phone", read_only=True)

    class Meta:
        model = PatientToken
        fields = ["id", "token_number", "status", "patient_name", "patient_phone", "estimated_time", "checked_in_at"]
