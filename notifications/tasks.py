from celery import shared_task
from django.utils import timezone


@shared_task
def send_30min_reminder(token_id: int):
    """
    Fires ~30 min before estimated time.
    Sends push (FCM) + SMS (AWS SNS) reminder to patient.
    Then schedules auto_complete_token to run 1 hour after this reminder fires.
    """
    from tokens.models import PatientToken
    from common.choices import TokenStatus
    from notifications.models import NotificationType, ReminderLog
    from notifications.services import send_push_notification, send_sms_notification

    try:
        token = PatientToken.objects.select_related("patient", "department").get(pk=token_id)
    except PatientToken.DoesNotExist:
        return

    if token.status not in [TokenStatus.WAITING, TokenStatus.CHECKED_IN]:
        return

    patient = token.patient
    dept_name = token.department.name
    title = "Appointment Reminder"
    body = (
        f"Your token #{token.token_number} for {dept_name} is coming up in ~30 minutes. "
        f"Please be available."
    )

    # Push notification via FCM
    send_push_notification(
        user=patient,
        title=title,
        body=body,
        notification_type=NotificationType.TOKEN_REMINDER,
        token=token,
    )

    # SMS via AWS SNS
    if patient.phone:
        send_sms_notification(patient.phone, f"Hospital Reminder: {body}")

    # Mark reminder log as sent
    ReminderLog.objects.filter(token=token, is_sent=False).update(
        is_sent=True,
        sent_at=timezone.now(),
    )

    # Schedule auto-complete 1 hour after this reminder fires
    auto_complete_token.apply_async(args=[token_id], countdown=3600)


@shared_task
def auto_complete_token(token_id: int):
    """
    Runs 1 hour after the 30-min reminder.
    Auto-completes the token and notifies the patient.
    """
    from tokens.models import PatientToken
    from common.choices import TokenStatus
    from notifications.models import NotificationType
    from notifications.services import send_push_notification, send_sms_notification

    try:
        token = PatientToken.objects.select_related("patient", "department").get(pk=token_id)
    except PatientToken.DoesNotExist:
        return

    # Only complete if still active — token admin may have already completed/cancelled it
    if token.status not in [TokenStatus.WAITING, TokenStatus.CHECKED_IN, TokenStatus.CALLED]:
        return

    token.status = TokenStatus.COMPLETED
    token.completed_at = timezone.now()
    token.save(update_fields=["status", "completed_at"])

    patient = token.patient
    dept_name = token.department.name
    title = "Token Completed"
    body = (
        f"Your token #{token.token_number} for {dept_name} has been marked as completed. "
        f"Thank you for visiting."
    )

    # Push notification via FCM
    send_push_notification(
        user=patient,
        title=title,
        body=body,
        notification_type=NotificationType.TOKEN_COMPLETED,
        token=token,
    )

    # SMS via AWS SNS
    if patient.phone:
        send_sms_notification(patient.phone, f"Hospital: {body}")
