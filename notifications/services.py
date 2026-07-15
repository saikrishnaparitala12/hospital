from django.utils import timezone
from accounts.models import FCMToken
from .models import NotificationLog, NotificationType, ReminderLog


def send_push_notification(user, title: str, body: str, notification_type: str, token=None) -> NotificationLog:
    """
    Send FCM push notification to all user devices.
    Replace the _send_fcm block with your actual Firebase Admin SDK call.
    """
    fcm_tokens = FCMToken.objects.filter(user=user).values_list("token", flat=True)
    fcm_response = None

    if fcm_tokens:
        fcm_response = _send_fcm(list(fcm_tokens), title, body)

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


def _send_fcm(tokens: list, title: str, body: str) -> dict:
    """
    Stub — replace with Firebase Admin SDK:

    import firebase_admin
    from firebase_admin import messaging
    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        tokens=tokens,
    )
    response = messaging.send_each_for_multicast(message)
    return {"success": response.success_count, "failure": response.failure_count}
    """
    return {"tokens": tokens, "status": "stub"}


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
