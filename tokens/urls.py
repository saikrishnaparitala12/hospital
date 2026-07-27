from django.urls import path
from .views import (
    IssueTokenView,
    MyTokensView,
    TokenDetailView,
    CheckInView,
    CancelTokenView,
    CompleteTokenView,
    MissedTokenView,
    QueueView,
    PatientListView,
    SendReminderView,
)

urlpatterns = [
    path("tokens/issue/", IssueTokenView.as_view(), name="token-issue"),
    path("tokens/my/", MyTokensView.as_view(), name="token-my"),
    path("tokens/patients/", PatientListView.as_view(), name="token-patients"),
    path("tokens/<int:pk>/", TokenDetailView.as_view(), name="token-detail"),
    path("tokens/<int:pk>/check-in/", CheckInView.as_view(), name="token-checkin"),
    path("tokens/<int:pk>/cancel/", CancelTokenView.as_view(), name="token-cancel"),
    path("tokens/<int:pk>/complete/", CompleteTokenView.as_view(), name="token-complete"),
    path("tokens/<int:pk>/missed/", MissedTokenView.as_view(), name="token-missed"),
    path("tokens/<int:pk>/send-reminder/", SendReminderView.as_view(), name="token-send-reminder"),
    path("departments/<int:dept_pk>/queue/", QueueView.as_view(), name="department-queue"),
]
