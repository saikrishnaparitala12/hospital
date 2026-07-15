from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from common.responses import success_response, error_response
from accounts.permissions import IsTokenAdminOrAdmin
from .serializers import TokenSerializer, IssueTokenSerializer, QueueSerializer
from . import services


class IssueTokenView(APIView):
    """Token admin issues a token on behalf of a patient."""
    permission_classes = [IsTokenAdminOrAdmin]

    def post(self, request):
        serializer = IssueTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = services.issue_token(
            user=request.user,
            department_id=serializer.validated_data["department_id"],
            issue_reason=serializer.validated_data.get("issue_reason", ""),
        )
        return success_response(TokenSerializer(token).data)


class MyTokensView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import PatientToken
        tokens = PatientToken.objects.filter(patient=request.user).order_by("-created_at")
        return success_response(TokenSerializer(tokens, many=True).data)


class TokenDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from common.exceptions import ServiceError
        from .models import PatientToken
        try:
            token = PatientToken.objects.get(pk=pk, patient=request.user)
        except PatientToken.DoesNotExist:
            raise ServiceError("Token not found.")
        return success_response(TokenSerializer(token).data)


class CheckInView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        token = services.check_in_token(request.user, pk)
        return success_response(TokenSerializer(token).data, message="Checked in successfully.")


class CancelTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        token = services.cancel_token(request.user, pk)
        return success_response(TokenSerializer(token).data, message="Token cancelled.")


class CompleteTokenView(APIView):
    """Token admin or admin marks a token as completed."""
    permission_classes = [IsTokenAdminOrAdmin]

    def post(self, request, pk):
        token = services.complete_token(pk)
        return success_response(TokenSerializer(token).data, message="Token completed.")


class MissedTokenView(APIView):
    """Token admin or admin marks a token as missed."""
    permission_classes = [IsTokenAdminOrAdmin]

    def post(self, request, pk):
        token = services.mark_missed(pk)
        return success_response(TokenSerializer(token).data, message="Token marked as missed.")


class QueueView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, dept_pk):
        date = request.query_params.get("date")
        if date:
            import datetime
            date = datetime.date.fromisoformat(date)
        queue = services.get_queue(dept_pk, date)
        return success_response(QueueSerializer(queue, many=True).data)


class SendReminderView(APIView):
    """
    Token admin manually sends a reminder notification to a patient.

    Sends both:
      - Push notification via FCM
      - SMS via AWS SNS

    POST /api/v1/tokens/<pk>/send-reminder/
    No payload required.
    """
    permission_classes = [IsTokenAdminOrAdmin]

    def post(self, request, pk):
        from common.exceptions import ServiceError
        from .models import PatientToken
        from common.choices import TokenStatus
        from notifications.services import send_push_notification, send_sms_notification
        from notifications.models import NotificationType

        try:
            token = PatientToken.objects.select_related("patient", "department").get(pk=pk)
        except PatientToken.DoesNotExist:
            raise ServiceError("Token not found.")

        if token.status not in [TokenStatus.WAITING, TokenStatus.CHECKED_IN]:
            return error_response("Reminder can only be sent for waiting or checked-in tokens.")

        patient = token.patient
        dept_name = token.department.name
        title = "Appointment Reminder"
        body = (
            f"Your token #{token.token_number} for {dept_name} — "
            f"your appointment is coming up soon. Please be available."
        )

        # Push notification (FCM)
        send_push_notification(
            user=patient,
            title=title,
            body=body,
            notification_type=NotificationType.TOKEN_REMINDER,
            token=token,
        )

        # SMS via AWS SNS
        if patient.phone:
            send_sms_notification(patient.phone, f"Hospital: {body}")

        return success_response(
            {"token_id": token.id, "token_number": token.token_number, "patient_phone": patient.phone},
            message="Reminder sent via push notification and SMS.",
        )
