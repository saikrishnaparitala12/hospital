from django.db import models
from common.models import BaseModel
from accounts.models import User
from tokens.models import PatientToken


class NotificationType(models.TextChoices):
    TOKEN_ISSUED = "token_issued", "Token Issued"
    TOKEN_REMINDER = "token_reminder", "Token Reminder"
    TOKEN_CALLED = "token_called", "Token Called"
    TOKEN_COMPLETED = "token_completed", "Token Completed"
    TOKEN_CANCELLED = "token_cancelled", "Token Cancelled"
    TOKEN_MISSED = "token_missed", "Token Missed"
    GENERAL = "general", "General"


class NotificationLog(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    token = models.ForeignKey(PatientToken, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    notification_type = models.CharField(max_length=30, choices=NotificationType.choices)
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    sent_at = models.DateTimeField(auto_now_add=True)
    fcm_response = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.notification_type} -> {self.user.phone}"


class ReminderLog(BaseModel):
    token = models.ForeignKey(PatientToken, on_delete=models.CASCADE, related_name="reminders")
    scheduled_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    is_sent = models.BooleanField(default=False)

    def __str__(self):
        return f"Reminder for Token #{self.token.token_number}"
