from django.urls import path
from .views import (
    NotificationListView,
    MarkAllReadView,
    MarkReadView,
    AdminSendNotificationView,
    AdminSendToDepartmentView,
    AdminSendToRoleView,
    AdminSendBulkPushView,
)

urlpatterns = [
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path("notifications/mark-all-read/", MarkAllReadView.as_view(), name="notification-mark-all-read"),
    path("notifications/<int:pk>/read/", MarkReadView.as_view(), name="notification-mark-read"),
    # Admin manual send to single user (push + optional SMS via AWS SNS)
    path("notifications/send/", AdminSendNotificationView.as_view(), name="notification-admin-send"),
    # Token admin / admin send to all patients in a department
    path("notifications/send-to-department/", AdminSendToDepartmentView.as_view(), name="notification-send-to-department"),
    # Admin send to all users with a specific role
    path("notifications/send-to-role/", AdminSendToRoleView.as_view(), name="notification-send-to-role"),
    # Token admin / admin send bulk push to multiple patients
    path("notifications/send-bulk/", AdminSendBulkPushView.as_view(), name="notification-send-bulk"),
]