from django.utils import timezone
from datetime import timedelta
from common.exceptions import ServiceError
from common.choices import TokenStatus
from departments.models import Department
from .models import DailyTokenSequence, PatientToken


def _get_sequence(department: Department, date) -> DailyTokenSequence:
    seq, _ = DailyTokenSequence.objects.get_or_create(department=department, date=date)
    return seq


def _estimate_time(department: Department, date, token_number: int):
    waiting_ahead = PatientToken.objects.filter(
        department=department,
        date=date,
        token_number__lt=token_number,
        status=TokenStatus.WAITING,
    ).count()
    minutes = waiting_ahead * department.average_service_time
    return timezone.now() + timedelta(minutes=minutes)


def issue_token(user, department_id: int, issue_reason: str = "", patient_id: int = None) -> PatientToken:
    """
    Issue a token for a patient.

    Args:
        user: The requesting user (token admin or the patient themselves)
        department_id: Department to issue token for
        issue_reason: Reason for visit
        patient_id: If provided (by token admin), issue token for this patient.
                    If None, issue token for the requesting user.
    """
    try:
        department = Department.objects.get(id=department_id, is_active=True)
    except Department.DoesNotExist:
        raise ServiceError("Department not found or inactive.")

    today = timezone.now().date()

    # Determine the patient - token admin can issue for others
    if patient_id:
        from accounts.models import User
        try:
            patient_user = User.objects.get(pk=patient_id, is_active=True)
        except User.DoesNotExist:
            raise ServiceError("Patient not found.")
        # Only token_admin or admin can issue tokens for other patients
        from accounts.models import Role
        if user.role not in [Role.TOKEN_ADMIN, Role.ADMIN] and not user.is_staff:
            raise ServiceError("Only token admin can issue tokens for other patients.")
    else:
        patient_user = user

    # Prevent duplicate active token for same dept on same day
    existing = PatientToken.objects.filter(
        patient=patient_user,
        department=department,
        date=today,
        status__in=[TokenStatus.WAITING, TokenStatus.CHECKED_IN],
    ).first()
    if existing:
        raise ServiceError("You already have an active token for this department today.")

    seq = _get_sequence(department, today)
    number = seq.next_number()
    estimated = _estimate_time(department, today, number)

    token = PatientToken.objects.create(
        patient=patient_user,
        department=department,
        token_number=number,
        date=today,
        estimated_time=estimated,
        issue_reason=issue_reason,
    )

    # Notify patient token issued (push + SMS)
    try:
        from notifications.services import notify_token_issued
        notify_token_issued(token)
    except Exception:
        pass

    # Schedule 30-min reminder before estimated time
    if estimated:
        from notifications.services import schedule_reminder
        from notifications.tasks import send_30min_reminder
        reminder_time = estimated - timedelta(minutes=30)
        schedule_reminder(token, reminder_time)
        delay_seconds = max(0, int((reminder_time - timezone.now()).total_seconds()))
        send_30min_reminder.apply_async(args=[token.id], countdown=delay_seconds)

    return token


def check_in_token(user, token_id: int) -> PatientToken:
    token = _get_user_token(user, token_id)
    if token.status != TokenStatus.WAITING:
        raise ServiceError("Token is not in waiting state.")
    token.status = TokenStatus.CHECKED_IN
    token.checked_in_at = timezone.now()
    token.save(update_fields=["status", "checked_in_at"])
    return token


def complete_token(token_id: int) -> PatientToken:
    token = _get_token(token_id)
    if token.status not in [TokenStatus.WAITING, TokenStatus.CHECKED_IN]:
        raise ServiceError("Token cannot be completed.")
    token.status = TokenStatus.COMPLETED
    token.completed_at = timezone.now()
    token.save(update_fields=["status", "completed_at"])
    return token


def cancel_token(user, token_id: int) -> PatientToken:
    token = _get_user_token(user, token_id)
    if token.status not in [TokenStatus.WAITING, TokenStatus.CHECKED_IN]:
        raise ServiceError("Token cannot be cancelled.")
    token.status = TokenStatus.CANCELLED
    token.save(update_fields=["status"])
    return token


def mark_missed(token_id: int) -> PatientToken:
    token = _get_token(token_id)
    if token.status != TokenStatus.WAITING:
        raise ServiceError("Token is not in waiting state.")
    token.status = TokenStatus.MISSED
    token.save(update_fields=["status"])
    return token


def get_queue(department_id: int, date=None):
    if date is None:
        date = timezone.now().date()
    return PatientToken.objects.filter(
        department_id=department_id,
        date=date,
        status__in=[TokenStatus.WAITING, TokenStatus.CHECKED_IN],
    ).select_related("patient", "counter").order_by("token_number")


def _get_user_token(user, token_id: int) -> PatientToken:
    try:
        return PatientToken.objects.get(id=token_id, patient=user)
    except PatientToken.DoesNotExist:
        raise ServiceError("Token not found.")


def _get_token(token_id: int) -> PatientToken:
    try:
        return PatientToken.objects.get(id=token_id)
    except PatientToken.DoesNotExist:
        raise ServiceError("Token not found.")