from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from common.responses import success_response, error_response
from accounts.permissions import IsTokenAdminOrAdmin
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


class AdminSendToDepartmentView(APIView):
    """
    Token admin / admin sends push notification to all patients
    with active tokens in a specific department.

    POST body:
      department_id  - target department id (required)
      title          - notification title (required)
      body           - notification message (required)
      data           - optional JSON data payload

    POST /api/v1/notifications/send-to-department/
    """
    permission_classes = [IsTokenAdminOrAdmin]

    def post(self, request):
        from common.exceptions import ServiceError
        from .models import NotificationType

        department_id = request.data.get("department_id")
        title = request.data.get("title")
        body = request.data.get("body")
        data = request.data.get("data")

        if not department_id or not title or not body:
            return error_response("department_id, title, and body are required.")

        from departments.models import Department
        if not Department.objects.filter(id=department_id, is_active=True).exists():
            raise ServiceError("Department not found or inactive.")

        fcm_response = services.send_push_to_department(
            department_id=int(department_id),
            title=title,
            body=body,
            notification_type=NotificationType.GENERAL,
            data=data,
        )

        return success_response(
            {
                "department_id": department_id,
                "fcm_response": fcm_response,
            },
            message="Department notification sent.",
        )


class AdminSendToRoleView(APIView):
    """
    Admin sends push notification to all users with a specific role.

    POST body:
      role   - target role (doctor, token_admin, patient, ambulance) (required)
      title  - notification title (required)
      body   - notification message (required)
      data   - optional JSON data payload

    POST /api/v1/notifications/send-to-role/
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        from accounts.models import Role
        from .models import NotificationType

        role = request.data.get("role")
        title = request.data.get("title")
        body = request.data.get("body")
        data = request.data.get("data")

        if not role or not title or not body:
            return error_response("role, title, and body are required.")

        valid_roles = [r.value for r in Role]
        if role not in valid_roles:
            return error_response(f"Invalid role. Valid roles: {', '.join(valid_roles)}")

        fcm_response = services.send_push_to_role(
            role=role,
            title=title,
            body=body,
            notification_type=NotificationType.GENERAL,
            data=data,
        )

        return success_response(
            {
                "role": role,
                "fcm_response": fcm_response,
            },
            message=f"Notification sent to all {role} users.",
        )


class AdminSendBulkPushView(APIView):
    """
    Token admin / admin sends push notification to multiple specific patients.

    POST body:
      user_ids  - list of patient user IDs (required)
      title     - notification title (required)
      body      - notification message (required)
      data      - optional JSON data payload

    POST /api/v1/notifications/send-bulk/
    """
    permission_classes = [IsTokenAdminOrAdmin]

    def post(self, request):
        from .models import NotificationType

        user_ids = request.data.get("user_ids")
        title = request.data.get("title")
        body = request.data.get("body")
        data = request.data.get("data")

        if not user_ids or not isinstance(user_ids, list) or len(user_ids) == 0:
            return error_response("user_ids must be a non-empty list.")
        if not title or not body:
            return error_response("title and body are required.")

        fcm_response = services.send_bulk_push_to_patients(
            user_ids=user_ids,
            title=title,
            body=body,
            notification_type=NotificationType.GENERAL,
            data=data,
        )

        return success_response(
            {
                "user_ids": user_ids,
                "count": len(user_ids),
                "fcm_response": fcm_response,
            },
            message=f"Bulk notification sent to {len(user_ids)} patients.",
        )