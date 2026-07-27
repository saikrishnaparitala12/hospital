from django.utils import timezone
from accounts.models import FCMToken
from .models import NotificationLog, NotificationType, ReminderLog


def send_push_notification(user, title: str, body: str, notification_type: str, token=None) -> NotificationLog:
    """
    Send FCM push notification to all user devices.
    Uses real Firebase Admin SDK if configured, otherwise falls back to stub.
    """
    fcm_tokens = FCMToken.objects.filter(user=user).values_list("token", flat=True)
    fcm_response = None

    if fcm_tokens:
        from .utils import send_fcm_notification
        fcm_response = send_fcm_notification(list(fcm_tokens), title, body)

    log = NotificationLog.objects.create(
        user=user,
        token=token,
        notification_type=notification_type,
        title=title,
        body=body,
        fcm_response=fcm_response,
    )
    return log


def send_sms_notification(phone: str, message: str) -> bool:
    """Send SMS via AWS SNS. Returns True on success."""
    try:
        from accounts.utils import send_sms_via_sns
        send_sms_via_sns(phone, message)
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"SNS SMS failed for {phone}: {e}")
        return False


def send_manual_notification(user, title: str, body: str, send_sms: bool = False, token=None) -> NotificationLog:
    """Admin-triggered manual notification: push + optional SMS."""
    log = send_push_notification(
        user=user,
        title=title,
        body=body,
        notification_type=NotificationType.GENERAL,
        token=token,
    )
    if send_sms and user.phone:
        send_sms_notification(user.phone, f"{title}: {body}")
    return log


def send_push_to_department(department_id: int, title: str, body: str, notification_type: str, data: dict = None) -> dict:
    """
    Send push notification to all patients with active tokens in a specific department today.
    Used for department-wide announcements (e.g., "Cardiology department is running 30 min late").
    """
    from .utils import send_fcm_to_department

    fcm_response = send_fcm_to_department(department_id, title, body, data)

    # Log the notification for all affected users
    from tokens.models import PatientToken
    from common.choices import TokenStatus
    from django.utils import timezone

    today = timezone.now().date()
    patients = (
        PatientToken.objects.filter(
            department_id=department_id,
            date=today,
            status__in=[TokenStatus.WAITING, TokenStatus.CHECKED_IN],
        )
        .select_related("patient")
        .distinct("patient")
    )

    for pt in patients:
        NotificationLog.objects.create(
            user=pt.patient,
            notification_type=notification_type,
            title=title,
            body=body,
            fcm_response=fcm_response,
        )

    return fcm_response


def send_push_to_role(role: str, title: str, body: str, notification_type: str, data: dict = None) -> dict:
    """
    Send push notification to all users with a specific role.
    e.g., send to all doctors, all token admins, etc.
    """
    from .utils import send_fcm_to_role
    from accounts.models import User

    fcm_response = send_fcm_to_role(role, title, body, data)

    users = User.objects.filter(role=role, is_active=True)
    for user in users:
        NotificationLog.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            body=body,
            fcm_response=fcm_response,
        )

    return fcm_response


def send_bulk_push_to_patients(user_ids: list, title: str, body: str, notification_type: str, data: dict = None) -> dict:
    """
    Send push notification to a specific list of patients by user IDs.
    Used when token admin wants to notify multiple specific patients.
    """
    from accounts.models import FCMToken

    tokens_list = list(
        FCMToken.objects.filter(user_id__in=user_ids)
        .values_list("token", flat=True)
    )

    fcm_response = None
    if tokens_list:
        from .utils import send_fcm_notification
        fcm_response = send_fcm_notification(tokens_list, title, body, data)

    for user_id in user_ids:
        from accounts.models import User
        try:
            user = User.objects.get(pk=user_id)
            NotificationLog.objects.create(
                user=user,
                notification_type=notification_type,
                title=title,
                body=body,
                fcm_response=fcm_response,
            )
        except User.DoesNotExist:
            continue

    return fcm_response


def notify_token_issued(patient_token) -> None:
    send_push_notification(
        user=patient_token.patient,
        title="Token Issued",
        body=f"Your token #{patient_token.token_number} for {patient_token.department.name} has been issued.",
        notification_type=NotificationType.TOKEN_ISSUED,
        token=patient_token,
    )


def notify_token_called(patient_token) -> None:
    send_push_notification(
        user=patient_token.patient,
        title="Your Turn!",
        body=f"Token #{patient_token.token_number} — please proceed to {patient_token.department.name}.",
        notification_type=NotificationType.TOKEN_CALLED,
        token=patient_token,
    )


def schedule_reminder(patient_token, scheduled_at) -> ReminderLog:
    return ReminderLog.objects.create(token=patient_token, scheduled_at=scheduled_at)


def get_user_notifications(user, unread_only=False):
    qs = NotificationLog.objects.filter(user=user)
    if unread_only:
        qs = qs.filter(is_read=False)
    return qs


def mark_all_read(user) -> None:
    NotificationLog.objects.filter(user=user, is_read=False).update(is_read=True)
