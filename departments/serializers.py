from rest_framework import serializers
from .models import Department, Counter, HospitalConfig


class CounterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Counter
        fields = ["id", "name", "is_active"]


class DepartmentSerializer(serializers.ModelSerializer):
    counters = CounterSerializer(many=True, read_only=True)

    class Meta:
        model = Department
        fields = ["id", "name", "description", "is_active", "average_service_time", "counters"]


class HospitalConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = HospitalConfig
        fields = ["id", "key", "value", "description"]
