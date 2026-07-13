from django.urls import path
from .views import NotificationListView, MarkAllReadView, MarkReadView

urlpatterns = [
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path("notifications/mark-all-read/", MarkAllReadView.as_view(), name="notification-mark-all-read"),
    path("notifications/<int:pk>/read/", MarkReadView.as_view(), name="notification-mark-read"),
]
