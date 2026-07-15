from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from common.responses import success_response, error_response
from .serializers import NotificationSerializer
from . import services


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        unread_only = request.query_params.get("unread") == "true"
        notifications = services.get_user_notifications(request.user, unread_only=unread_only)
        return success_response(NotificationSerializer(notifications, many=True).data)


class MarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        services.mark_all_read(request.user)
        return success_response(message="All notifications marked as read.")


class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .models import NotificationLog
        NotificationLog.objects.filter(id=pk, user=request.user).update(is_read=True)
        return success_response(message="Notification marked as read.")


class AdminSendNotificationView(APIView):
    """
    Admin manually sends a notification to a specific user.
    Supports both push (FCM) and SMS (AWS SNS).

    POST body:
      user_id   - target user id (required)
      title     - notification title (required)
      body      - notification message (required)
      send_sms  - true/false, whether to also send SMS via AWS SNS (optional, default false)
      token_id  - link to a PatientToken (optional)
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        from accounts.models import User
        from common.exceptions import ServiceError

        user_id = request.data.get("user_id")
        title = request.data.get("title")
        body = request.data.get("body")
        send_sms = str(request.data.get("send_sms", "false")).lower() == "true"
        token_id = request.data.get("token_id")

        if not user_id or not title or not body:
            return error_response("user_id, title, and body are required.")

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise ServiceError("User not found.")

        patient_token = None
        if token_id:
            from tokens.models import PatientToken
            patient_token = PatientToken.objects.filter(pk=token_id).first()

        log = services.send_manual_notification(
            user=user,
            title=title,
            body=body,
            send_sms=send_sms,
            token=patient_token,
        )
        return success_response(
            NotificationSerializer(log).data,
            message="Notification sent.",
        )
