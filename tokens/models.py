from django.db import models
from common.models import BaseModel
from common.choices import TokenStatus
from accounts.models import User
from departments.models import Department, Counter


class DailyTokenSequence(BaseModel):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="daily_sequences")
    date = models.DateField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("department", "date")

    def __str__(self):
        return f"{self.department.name} - {self.date} - #{self.last_number}"

    def next_number(self) -> int:
        self.last_number += 1
        self.save(update_fields=["last_number"])
        return self.last_number


class PatientToken(BaseModel):
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tokens")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="tokens")
    counter = models.ForeignKey(Counter, on_delete=models.SET_NULL, null=True, blank=True, related_name="tokens")
    token_number = models.PositiveIntegerField()
    date = models.DateField()
    status = models.CharField(max_length=20, choices=TokenStatus.choices, default=TokenStatus.WAITING)
    estimated_time = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    issue_reason = models.TextField(blank=True, help_text="Patient's complaint / reason for visit")
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("department", "date", "token_number")
        ordering = ["date", "token_number"]

    def __str__(self):
        return f"Token #{self.token_number} - {self.department.name} ({self.status})"
