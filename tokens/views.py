from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from common.responses import success_response, error_response
from accounts.permissions import IsTokenAdminOrAdmin
from .serializers import (
    CallNextSerializer,
    IssueTokenSerializer,
    QueueSerializer,
    TokenConfigSerializer,
    TokenSerializer,
)
from . import services


class IssueTokenView(APIView):
    """
    Issue a token.
    - Reception/token admin can issue for any patient (patient_id or patient_phone).
    - Regular patients can issue for themselves (omit patient_id).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = IssueTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = services.issue_token(
            user=request.user,
            department_id=serializer.validated_data["department_id"],
            issue_reason=serializer.validated_data.get("issue_reason", ""),
            patient_id=serializer.validated_data.get("patient_id"),
            patient_phone=serializer.validated_data.get("patient_phone", ""),
            patient_name=serializer.validated_data.get("patient_name", ""),
            counter_id=serializer.validated_data.get("counter_id"),
            is_emergency=serializer.validated_data.get("is_emergency", False),
        )
        return success_response(TokenSerializer(token).data)


class MyTokensView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import PatientToken
        tokens = PatientToken.objects.filter(patient=request.user).select_related("department", "counter").order_by("-created_at")
        return success_response(TokenSerializer(tokens, many=True).data)


class MyActiveTodayTokensView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tokens = services.get_today_active_tokens(request.user)
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


class QueueSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, dept_pk):
        date = request.query_params.get("date")
        if date:
            import datetime
            date = datetime.date.fromisoformat(date)

        summary = services.get_queue_summary(dept_pk, date)
        data = {
            "department_id": summary["department_id"],
            "department_name": summary["department_name"],
            "date": summary["date"].isoformat(),
            "average_service_time": summary["average_service_time"],
            "reminder_threshold_tokens": summary["reminder_threshold_tokens"],
            "waiting_count": summary["waiting_count"],
            "emergency_count": summary["emergency_count"],
            "current_serving": (
                QueueSerializer(summary["current_serving"]).data
                if summary["current_serving"]
                else None
            ),
            "up_next": (
                QueueSerializer(summary["up_next"]).data
                if summary["up_next"]
                else None
            ),
        }
        return success_response(data)


class CallNextTokenView(APIView):
    permission_classes = [IsTokenAdminOrAdmin]

    def post(self, request, dept_pk):
        serializer = CallNextSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = services.call_next_token(
            department_id=dept_pk,
            counter_id=serializer.validated_data.get("counter_id"),
            complete_current=serializer.validated_data.get("complete_current", True),
        )
        return success_response(TokenSerializer(token).data, message="Next token called.")


class TokenConfigView(APIView):
    permission_classes = [IsTokenAdminOrAdmin]

    def _get_department(self, dept_pk):
        from common.exceptions import ServiceError
        from departments.models import Department

        try:
            return Department.objects.get(pk=dept_pk, is_active=True)
        except Department.DoesNotExist:
            raise ServiceError("Department not found or inactive.")

    def get(self, request, dept_pk):
        return success_response(TokenConfigSerializer(self._get_department(dept_pk)).data)

    def patch(self, request, dept_pk):
        department = self._get_department(dept_pk)
        serializer = TokenConfigSerializer(department, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        services.refresh_queue_estimates(department)
        return success_response(serializer.data, message="Token timing config updated.")


class PatientListView(APIView):
    """
    Token admin lists all patients to select one for token issuance.
    Supports search by phone or name.

    GET /api/v1/tokens/patients/?search=phone_or_name
    """
    permission_classes = [IsTokenAdminOrAdmin]

    def get(self, request):
        from accounts.models import User, Role
        from accounts.serializers import UserSerializer

        search = request.query_params.get("search", "").strip()
        patients = User.objects.filter(role=Role.PATIENT, is_active=True)

        if search:
            from django.db.models import Q
            patients = patients.filter(
                Q(phone__icontains=search) | Q(full_name__icontains=search)
            )

        patients = patients.order_by("full_name")[:50]
        return success_response(UserSerializer(patients, many=True).data)


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
