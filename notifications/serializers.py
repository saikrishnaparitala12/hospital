from rest_framework import serializers
from .models import NotificationLog


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationLog
        fields = ["id", "notification_type", "title", "body", "is_read", "sent_at"]
        read_only_fields = fields
