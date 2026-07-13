from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from common.responses import success_response
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
