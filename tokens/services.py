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


def issue_token(user, department_id: int) -> PatientToken:
    try:
        department = Department.objects.get(id=department_id, is_active=True)
    except Department.DoesNotExist:
        raise ServiceError("Department not found or inactive.")

    today = timezone.now().date()

    # Prevent duplicate active token for same dept on same day
    existing = PatientToken.objects.filter(
        patient=user,
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
        patient=user,
        department=department,
        token_number=number,
        date=today,
        estimated_time=estimated,
    )
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
