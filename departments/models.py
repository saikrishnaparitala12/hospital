from django.db import models
from common.models import BaseModel


class Department(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    average_service_time = models.PositiveIntegerField(default=10, help_text="Minutes per patient")

    def __str__(self):
        return self.name


class Counter(BaseModel):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="counters")
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.department.name} - {self.name}"


class HospitalConfig(BaseModel):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.key} = {self.value}"

    class Meta:
        verbose_name = "Hospital Configuration"
