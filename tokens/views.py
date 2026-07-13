from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from common.responses import success_response
from .serializers import TokenSerializer, IssueTokenSerializer, QueueSerializer
from . import services


class IssueTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = IssueTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = services.issue_token(request.user, serializer.validated_data["department_id"])
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
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        token = services.complete_token(pk)
        return success_response(TokenSerializer(token).data, message="Token completed.")


class MissedTokenView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        token = services.mark_missed(pk)
        return success_response(TokenSerializer(token).data, message="Token marked as missed.")


class QueueView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, dept_pk):
        date = request.query_params.get("date")
        if date:
            from datetime import date as date_type
            import datetime
            date = datetime.date.fromisoformat(date)
        queue = services.get_queue(dept_pk, date)
        return success_response(QueueSerializer(queue, many=True).data)
