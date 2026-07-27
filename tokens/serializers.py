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
            "checked_in_at", "completed_at",
            "issue_reason", "notes",
            "created_at",
        ]
        read_only_fields = ["id", "token_number", "date", "status", "estimated_time", "created_at"]


class IssueTokenSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(required=False, help_text="Patient user ID. Token admin provides this to issue for a patient. Patient self-service omits this.")
    department_id = serializers.IntegerField()
    issue_reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_patient_id(self, value):
        from accounts.models import User
        try:
            user = User.objects.get(pk=value, is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError("Patient not found.")
        return value


class QueueSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    patient_phone = serializers.CharField(source="patient.phone", read_only=True)

    class Meta:
        model = PatientToken
        fields = ["id", "token_number", "status", "patient_name", "patient_phone", "estimated_time", "checked_in_at"]
