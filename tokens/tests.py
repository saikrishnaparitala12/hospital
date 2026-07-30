from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from common.choices import TokenStatus
from departments.models import Counter, Department
from tokens.models import PatientToken


class TokenWorkflowAPITests(APITestCase):
    def setUp(self):
        self.department = Department.objects.create(
            name="General Medicine",
            average_service_time=5,
            reminder_threshold_tokens=2,
        )
        self.counter = Counter.objects.create(department=self.department, name="Room 4")
        self.patient = User.objects.create_user(
            phone="9000000001",
            password="pass123",
            full_name="Asha Patient",
            role=Role.PATIENT,
        )
        self.reception = User.objects.create_user(
            phone="9000000002",
            password="pass123",
            full_name="Reception",
            role=Role.TOKEN_ADMIN,
        )

    @patch("tokens.services._schedule_estimate_reminder")
    @patch("notifications.services.notify_token_issued")
    def test_patient_can_issue_self_service_token(self, _notify, _schedule):
        self.client.force_authenticate(self.patient)

        response = self.client.post(
            reverse("token-issue"),
            {"department_id": self.department.id, "issue_reason": "Fever"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        token = PatientToken.objects.get()
        self.assertEqual(token.patient, self.patient)
        self.assertFalse(token.is_emergency)
        self.assertEqual(response.data["data"]["queue_position"], 1)
        self.assertTrue(response.data["data"]["is_next"])

    @patch("tokens.services._schedule_estimate_reminder")
    @patch("notifications.services.notify_token_issued")
    def test_reception_can_issue_by_phone_and_emergency_jumps_queue(self, _notify, _schedule):
        self.client.force_authenticate(self.reception)

        first = self.client.post(
            reverse("token-issue"),
            {
                "department_id": self.department.id,
                "patient_phone": "9000000011",
                "patient_name": "Normal Patient",
            },
            format="json",
        )
        emergency = self.client.post(
            reverse("token-issue"),
            {
                "department_id": self.department.id,
                "patient_phone": "9000000012",
                "patient_name": "Emergency Patient",
                "is_emergency": True,
            },
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(emergency.status_code, 200)
        self.assertTrue(User.objects.filter(phone="9000000012", role=Role.PATIENT).exists())

        queue = self.client.get(reverse("department-queue", args=[self.department.id]))

        self.assertEqual(queue.status_code, 200)
        self.assertEqual([item["token_number"] for item in queue.data["data"]], [2, 1])
        self.assertEqual(queue.data["data"][0]["queue_position"], 1)
        self.assertTrue(queue.data["data"][0]["is_emergency"])

    @patch("tokens.services._schedule_estimate_reminder")
    @patch("notifications.services.notify_token_issued")
    def test_patient_cannot_mark_self_service_token_as_emergency(self, _notify, _schedule):
        self.client.force_authenticate(self.patient)

        response = self.client.post(
            reverse("token-issue"),
            {
                "department_id": self.department.id,
                "issue_reason": "Fever",
                "is_emergency": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PatientToken.objects.exists())

    @patch("tokens.services._notify_threshold_tokens")
    @patch("notifications.services.notify_token_called")
    def test_reception_can_call_next_token(self, _notify_called, _notify_threshold):
        today = timezone.now().date()
        PatientToken.objects.create(
            patient=self.patient,
            department=self.department,
            token_number=1,
            date=today,
        )
        PatientToken.objects.create(
            patient=User.objects.create_user(
                phone="9000000013",
                password="pass123",
                role=Role.PATIENT,
            ),
            department=self.department,
            token_number=2,
            date=today,
            is_emergency=True,
        )
        self.client.force_authenticate(self.reception)

        response = self.client.post(
            reverse("department-queue-call-next", args=[self.department.id]),
            {"counter_id": self.counter.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], TokenStatus.CALLED)
        self.assertEqual(response.data["data"]["token_number"], 2)
        self.assertEqual(response.data["data"]["counter"], self.counter.id)
