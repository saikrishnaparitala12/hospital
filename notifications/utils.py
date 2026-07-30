import os
import logging
from django.conf import settings
import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

_firebase_app = None


def get_firebase_app():
    """Initialize Firebase app once (singleton pattern)."""
    global _firebase_app
    if _firebase_app is None:
        cred_path = settings.FIREBASE_CREDENTIALS_PATH
        if not os.path.isabs(str(cred_path)):
            cred_path = settings.BASE_DIR / cred_path

        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            _firebase_app = firebase_admin.initialize_app(
                cred,
                options={"databaseURL": settings.FIREBASE_DATABASE_URL} if settings.FIREBASE_DATABASE_URL else None,
            )
            logger.info("Firebase app initialized successfully.")
        else:
            logger.warning(
                f"Firebase credentials not found at {cred_path}. "
                "Push notifications will be stubbed."
            )
    return _firebase_app


def send_fcm_notification(tokens: list, title: str, body: str, data: dict = None) -> dict:
    """
    Send FCM push notification to a list of device tokens.
    
    Args:
        tokens: List of FCM device tokens
        title: Notification title
        body: Notification body
        data: Optional data payload dict
        
    Returns:
        dict with success/failure counts
    """
    if not tokens:
        return {"success": 0, "failure": 0, "status": "no_tokens"}

    app = get_firebase_app()
    if app is None:
        return {"tokens": tokens, "status": "stub", "reason": "No Firebase credentials"}

    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            tokens=tokens,
            data=data or {},
        )
        response = messaging.send_each_for_multicast(message)
        return {
            "success": response.success_count,
            "failure": response.failure_count,
            "responses": [
                {
                    "index": i,
                    "success": resp.success,
                    "message_id": resp.message_id,
                    "error": str(resp.exception) if resp.exception else None,
                }
                for i, resp in enumerate(response.responses)
            ],
        }
    except Exception as e:
        logger.exception(f"FCM send failed: {e}")
        return {"success": 0, "failure": len(tokens), "error": str(e)}


def send_fcm_to_department(department_id: int, title: str, body: str, data: dict = None) -> dict:
    """
    Send FCM notification to all users who have tokens in a specific department.
    This handles department-specific push notifications.
    
    Args:
        department_id: Department ID to target
        title: Notification title
        body: Notification body
        data: Optional data payload
        
    Returns:
        dict with success/failure counts
    """
    from accounts.models import FCMToken
    from tokens.models import PatientToken
    from common.choices import TokenStatus
    from django.utils import timezone

    # Get all patients who have active tokens in this department today
    today = timezone.now().date()
    patient_ids = (
        PatientToken.objects.filter(
            department_id=department_id,
            date=today,
            status__in=[TokenStatus.WAITING, TokenStatus.CHECKED_IN, TokenStatus.CALLED],
        )
        .values_list("patient_id", flat=True)
        .distinct()
    )

    # Get FCM tokens for those patients
    tokens_list = list(
        FCMToken.objects.filter(user_id__in=list(patient_ids))
        .values_list("token", flat=True)
    )

    if not tokens_list:
        return {"success": 0, "failure": 0, "status": "no_tokens_for_department"}

    return send_fcm_notification(tokens_list, title, body, data)


def send_fcm_to_role(role: str, title: str, body: str, data: dict = None) -> dict:
    """
    Send FCM notification to all users with a specific role.
    e.g., all doctors, all token admins, all patients with tokens today.
    
    Args:
        role: The user role to target (doctor, token_admin, patient, etc.)
        title: Notification title
        body: Notification body
        data: Optional data payload
        
    Returns:
        dict with success/failure counts
    """
    from accounts.models import FCMToken, User

    user_ids = User.objects.filter(role=role, is_active=True).values_list("id", flat=True)
    tokens_list = list(
        FCMToken.objects.filter(user_id__in=list(user_ids))
        .values_list("token", flat=True)
    )

    if not tokens_list:
        return {"success": 0, "failure": 0, "status": "no_tokens_for_role"}

    return send_fcm_notification(tokens_list, title, body, data)


def send_fcm_to_all_active_patients(department_id: int = None, title: str = "", body: str = "", data: dict = None) -> dict:
    """
    Send FCM to all patients who have active tokens today.
    Optionally filter by department.
    """
    from accounts.models import FCMToken
    from tokens.models import PatientToken
    from common.choices import TokenStatus
    from django.utils import timezone

    today = timezone.now().date()
    filters = {
        "date": today,
        "status__in": [TokenStatus.WAITING, TokenStatus.CHECKED_IN, TokenStatus.CALLED],
    }
    if department_id:
        filters["department_id"] = department_id

    patient_ids = (
        PatientToken.objects.filter(**filters)
        .values_list("patient_id", flat=True)
        .distinct()
    )

    tokens_list = list(
        FCMToken.objects.filter(user_id__in=list(patient_ids))
        .values_list("token", flat=True)
    )

    if not tokens_list:
        return {"success": 0, "failure": 0, "status": "no_active_patients"}

    return send_fcm_notification(tokens_list, title, body, data)
