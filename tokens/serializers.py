from rest_framework import serializers
from .models import PatientToken
from departments.models import Department


class QueueSnapshotMixin:
    def _snapshot(self, obj):
        if not hasattr(obj, "_queue_snapshot"):
            from . import services
            obj._queue_snapshot = services.get_token_queue_snapshot(obj)
        return obj._queue_snapshot

    def get_queue_position(self, obj):
        return self._snapshot(obj)["queue_position"]

    def get_tokens_away(self, obj):
        return self._snapshot(obj)["tokens_away"]

    def get_people_ahead(self, obj):
        return self._snapshot(obj)["people_ahead"]

    def get_estimated_wait_minutes(self, obj):
        return self._snapshot(obj)["estimated_wait_minutes"]

    def get_is_next(self, obj):
        return self._snapshot(obj)["is_next"]

    def get_current_serving_token_number(self, obj):
        return self._snapshot(obj)["current_serving_token_number"]

    def get_reminder_threshold_tokens(self, obj):
        return self._snapshot(obj)["reminder_threshold_tokens"]


class TokenSerializer(QueueSnapshotMixin, serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    counter_name = serializers.CharField(source="counter.name", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    patient_phone = serializers.CharField(source="patient.phone", read_only=True)
    queue_position = serializers.SerializerMethodField()
    tokens_away = serializers.SerializerMethodField()
    people_ahead = serializers.SerializerMethodField()
    estimated_wait_minutes = serializers.SerializerMethodField()
    is_next = serializers.SerializerMethodField()
    current_serving_token_number = serializers.SerializerMethodField()
    reminder_threshold_tokens = serializers.SerializerMethodField()

    class Meta:
        model = PatientToken
        fields = [
            "id", "token_number", "date", "status",
            "department", "department_name",
            "counter", "counter_name",
            "patient_name", "patient_phone", "estimated_time",
            "queue_position", "tokens_away", "people_ahead",
            "estimated_wait_minutes", "is_next", "current_serving_token_number",
            "reminder_threshold_tokens",
            "checked_in_at", "called_at", "completed_at",
            "is_emergency", "issue_reason", "notes",
            "created_at",
        ]
        read_only_fields = [
            "id", "token_number", "date", "status", "estimated_time",
            "queue_position", "tokens_away", "people_ahead",
            "estimated_wait_minutes", "is_next", "current_serving_token_number",
            "reminder_threshold_tokens", "created_at",
        ]


class IssueTokenSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(required=False, help_text="Existing patient user ID. Reception/admin only.")
    patient_phone = serializers.CharField(required=False, allow_blank=True, help_text="Patient phone number. Reception/admin can use this instead of patient_id.")
    patient_name = serializers.CharField(required=False, allow_blank=True, help_text="Patient name to store when reception creates/finds by phone.")
    department_id = serializers.IntegerField()
    counter_id = serializers.IntegerField(required=False)
    is_emergency = serializers.BooleanField(required=False, default=False)
    issue_reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs.get("patient_id") and attrs.get("patient_phone"):
            raise serializers.ValidationError("Use either patient_id or patient_phone, not both.")
        return attrs

    def validate_patient_id(self, value):
        from accounts.models import User
        try:
            user = User.objects.get(pk=value, is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError("Patient not found.")
        return value


class QueueSerializer(QueueSnapshotMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    patient_phone = serializers.CharField(source="patient.phone", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    counter_name = serializers.CharField(source="counter.name", read_only=True)
    queue_position = serializers.SerializerMethodField()
    tokens_away = serializers.SerializerMethodField()
    people_ahead = serializers.SerializerMethodField()
    estimated_wait_minutes = serializers.SerializerMethodField()
    is_next = serializers.SerializerMethodField()
    current_serving_token_number = serializers.SerializerMethodField()
    reminder_threshold_tokens = serializers.SerializerMethodField()

    class Meta:
        model = PatientToken
        fields = [
            "id", "token_number", "status", "department_name",
            "patient_name", "patient_phone", "counter", "counter_name",
            "is_emergency", "estimated_time", "estimated_wait_minutes",
            "queue_position", "tokens_away", "people_ahead", "is_next",
            "current_serving_token_number", "reminder_threshold_tokens",
            "checked_in_at", "called_at",
        ]


class CallNextSerializer(serializers.Serializer):
    counter_id = serializers.IntegerField(required=False)
    complete_current = serializers.BooleanField(required=False, default=True)


class TokenConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "average_service_time", "reminder_threshold_tokens"]
        read_only_fields = ["id", "name"]

    def validate_average_service_time(self, value):
        if value < 1:
            raise serializers.ValidationError("Average service time must be at least 1 minute.")
        return value
