from django.urls import path
from .views import DepartmentListCreateView, DepartmentDetailView, CounterListCreateView

urlpatterns = [
    path("departments/", DepartmentListCreateView.as_view(), name="department-list"),
    path("departments/<int:pk>/", DepartmentDetailView.as_view(), name="department-detail"),
    path("departments/<int:dept_pk>/counters/", CounterListCreateView.as_view(), name="counter-list"),
]
