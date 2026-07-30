from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from common.exceptions import ServiceError
from common.choices import TokenStatus
from departments.models import Counter, Department
from .models import DailyTokenSequence, PatientToken


ACTIVE_QUEUE_STATUSES = [
    TokenStatus.WAITING,
    TokenStatus.CHECKED_IN,
    TokenStatus.CALLED,
]

WAITING_QUEUE_STATUSES = [
    TokenStatus.WAITING,
    TokenStatus.CHECKED_IN,
]


def _is_token_admin(user) -> bool:
    from accounts.models import Role

    return bool(
        user
        and user.is_authenticated
        and (user.role in [Role.TOKEN_ADMIN, Role.ADMIN] or user.is_staff)
    )


def _get_department(department_id: int) -> Department:
    try:
        return Department.objects.get(id=department_id, is_active=True)
    except Department.DoesNotExist:
        raise ServiceError("Department not found or inactive.")


def _get_counter(counter_id: int, department: Department) -> Counter:
    try:
        return Counter.objects.get(id=counter_id, department=department, is_active=True)
    except Counter.DoesNotExist:
        raise ServiceError("Counter not found or inactive for this department.")


def _get_sequence(department: Department, date) -> DailyTokenSequence:
    seq, _ = DailyTokenSequence.objects.select_for_update().get_or_create(
        department=department,
        date=date,
    )
    return seq


def _ordered_active_queue(department: Department, date):
    status_order = Case(
        When(status=TokenStatus.CALLED, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    return (
        PatientToken.objects.filter(
            department=department,
            date=date,
            status__in=ACTIVE_QUEUE_STATUSES,
        )
        .select_related("patient", "department", "counter")
        .annotate(_status_order=status_order)
        .order_by("_status_order", "-is_emergency", "token_number")
    )


def _ordered_waiting_queue(department: Department, date):
    return (
        PatientToken.objects.filter(
            department=department,
            date=date,
            status__in=WAITING_QUEUE_STATUSES,
        )
        .select_related("patient", "department", "counter")
        .order_by("-is_emergency", "token_number")
    )


def refresh_queue_estimates(department: Department, date=None):
    if date is None:
        date = timezone.now().date()

    now = timezone.now()
    current_serving_count = PatientToken.objects.filter(
        department=department,
        date=date,
        status=TokenStatus.CALLED,
    ).count()
    queued_tokens = list(_ordered_waiting_queue(department, date))

    for index, token in enumerate(queued_tokens):
        minutes = (current_serving_count + index) * department.average_service_time
        token.estimated_time = now + timedelta(minutes=minutes)
        token.updated_at = now

    if queued_tokens:
        PatientToken.objects.bulk_update(queued_tokens, ["estimated_time", "updated_at"])

    return queued_tokens


def _estimate_time(department: Department, date, token_number: int, is_emergency: bool = False):
    current_serving_count = PatientToken.objects.filter(
        department=department,
        date=date,
        status=TokenStatus.CALLED,
    ).count()

    waiting_qs = PatientToken.objects.filter(
        department=department,
        date=date,
        status__in=WAITING_QUEUE_STATUSES,
    )

    if is_emergency:
        waiting_ahead = waiting_qs.filter(is_emergency=True, token_number__lt=token_number).count()
    else:
        waiting_ahead = waiting_qs.filter(token_number__lt=token_number).count()

    minutes = (current_serving_count + waiting_ahead) * department.average_service_time
    return timezone.now() + timedelta(minutes=minutes)


def _resolve_patient_for_issue(user, patient_id: int = None, patient_phone: str = "", patient_name: str = ""):
    from accounts.models import Role, User

    patient_phone = (patient_phone or "").strip()
    patient_name = (patient_name or "").strip()

    if _is_token_admin(user):
        if patient_id:
            try:
                patient_user = User.objects.get(pk=patient_id, is_active=True)
            except User.DoesNotExist:
                raise ServiceError("Patient not found.")
        elif patient_phone:
            patient_user, created = User.objects.get_or_create(
                phone=patient_phone,
                defaults={
                    "full_name": patient_name,
                    "role": Role.PATIENT,
                    "is_active": True,
                },
            )
            if created:
                patient_user.set_unusable_password()
                patient_user.save(update_fields=["password"])
            elif patient_name and not patient_user.full_name:
                patient_user.full_name = patient_name
                patient_user.save(update_fields=["full_name"])
        else:
            raise ServiceError("Provide patient_id or patient_phone to issue a reception token.")

        if patient_user.role != Role.PATIENT:
            raise ServiceError("Selected user is not a patient.")
        if not patient_user.is_active:
            raise ServiceError("Patient account is inactive.")
        return patient_user

    if user.role != Role.PATIENT:
        raise ServiceError("Only patients can issue self-service tokens.")

    if patient_id and patient_id != user.id:
        raise ServiceError("Patients can only issue tokens for themselves.")

    if patient_phone and patient_phone != user.phone:
        raise ServiceError("Patients can only issue tokens for themselves.")

    return user


def _schedule_estimate_reminder(token: PatientToken) -> None:
    if not token.estimated_time:
        return

    try:
        from notifications.services import schedule_reminder
        from notifications.tasks import send_30min_reminder

        reminder_time = token.estimated_time - timedelta(minutes=30)
        schedule_reminder(token, reminder_time)
        delay_seconds = max(0, int((reminder_time - timezone.now()).total_seconds()))
        send_30min_reminder.apply_async(args=[token.id], countdown=delay_seconds)
    except Exception:
        pass


@transaction.atomic
def issue_token(
    user,
    department_id: int,
    issue_reason: str = "",
    patient_id: int = None,
    patient_phone: str = "",
    patient_name: str = "",
    counter_id: int = None,
    is_emergency: bool = False,
) -> PatientToken:
    """
    Issue a token for a patient.

    Args:
        user: The requesting user (reception/token admin or the patient themselves)
        department_id: Department to issue token for
        issue_reason: Reason for visit
        patient_id: Existing patient user ID. Reception/admin only.
        patient_phone: Patient phone. Reception/admin can create or reuse a patient.
        patient_name: Optional name to store when reception creates/finds by phone.
        counter_id: Optional counter/room assignment for the visit.
        is_emergency: Reception/admin-only priority flag.
    """
    department = _get_department(department_id)
    counter = _get_counter(counter_id, department) if counter_id else None
    today = timezone.now().date()

    if is_emergency and not _is_token_admin(user):
        raise ServiceError("Only reception or admin can mark a token as emergency.")

    patient_user = _resolve_patient_for_issue(
        user=user,
        patient_id=patient_id,
        patient_phone=patient_phone,
        patient_name=patient_name,
    )

    # Prevent duplicate active token for same dept on same day
    existing = PatientToken.objects.filter(
        patient=patient_user,
        department=department,
        date=today,
        status__in=ACTIVE_QUEUE_STATUSES,
    ).first()
    if existing:
        raise ServiceError("You already have an active token for this department today.")

    seq = _get_sequence(department, today)
    number = seq.next_number()
    estimated = _estimate_time(department, today, number, is_emergency=is_emergency)

    token = PatientToken.objects.create(
        patient=patient_user,
        department=department,
        counter=counter,
        token_number=number,
        date=today,
        estimated_time=estimated,
        issue_reason=issue_reason,
        is_emergency=is_emergency,
    )
    refresh_queue_estimates(department, today)
    token.refresh_from_db()

    # Notify patient token issued (push + SMS)
    try:
        from notifications.services import notify_token_issued
        notify_token_issued(token)
    except Exception:
        pass

    _schedule_estimate_reminder(token)

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
    if token.status not in ACTIVE_QUEUE_STATUSES:
        raise ServiceError("Token cannot be completed.")
    token.status = TokenStatus.COMPLETED
    token.completed_at = timezone.now()
    token.save(update_fields=["status", "completed_at"])
    refresh_queue_estimates(token.department, token.date)
    return token


def cancel_token(user, token_id: int) -> PatientToken:
    token = _get_user_token(user, token_id)
    if token.status not in [TokenStatus.WAITING, TokenStatus.CHECKED_IN]:
        raise ServiceError("Token cannot be cancelled.")
    token.status = TokenStatus.CANCELLED
    token.save(update_fields=["status"])
    refresh_queue_estimates(token.department, token.date)
    return token


def mark_missed(token_id: int) -> PatientToken:
    token = _get_token(token_id)
    if token.status not in ACTIVE_QUEUE_STATUSES:
        raise ServiceError("Token is not active.")
    token.status = TokenStatus.MISSED
    token.save(update_fields=["status"])
    refresh_queue_estimates(token.department, token.date)
    return token


def get_queue(department_id: int, date=None):
    if date is None:
        date = timezone.now().date()
    department = _get_department(department_id)
    return _ordered_active_queue(department, date)


def get_today_active_tokens(user):
    today = timezone.now().date()
    return (
        PatientToken.objects.filter(
            patient=user,
            date=today,
            status__in=ACTIVE_QUEUE_STATUSES,
        )
        .select_related("department", "counter")
        .order_by("-is_emergency", "estimated_time", "token_number")
    )


def get_token_queue_snapshot(token: PatientToken) -> dict:
    if token.status not in ACTIVE_QUEUE_STATUSES:
        return {
            "queue_position": None,
            "tokens_away": None,
            "people_ahead": None,
            "estimated_wait_minutes": None,
            "is_next": False,
            "current_serving_token_id": None,
            "current_serving_token_number": None,
            "reminder_threshold_tokens": token.department.reminder_threshold_tokens,
        }

    current_serving = (
        PatientToken.objects.filter(
            department=token.department,
            date=token.date,
            status=TokenStatus.CALLED,
        )
        .select_related("counter")
        .order_by("called_at", "token_number")
        .first()
    )

    current_id = current_serving.id if current_serving else None
    current_number = current_serving.token_number if current_serving else None

    if token.status == TokenStatus.CALLED:
        return {
            "queue_position": 0,
            "tokens_away": 0,
            "people_ahead": 0,
            "estimated_wait_minutes": 0,
            "is_next": False,
            "current_serving_token_id": current_id,
            "current_serving_token_number": current_number,
            "reminder_threshold_tokens": token.department.reminder_threshold_tokens,
        }

    waiting_tokens = list(_ordered_waiting_queue(token.department, token.date))
    token_ids = [queued.id for queued in waiting_tokens]

    if token.id not in token_ids:
        return {
            "queue_position": None,
            "tokens_away": None,
            "people_ahead": None,
            "estimated_wait_minutes": None,
            "is_next": False,
            "current_serving_token_id": current_id,
            "current_serving_token_number": current_number,
            "reminder_threshold_tokens": token.department.reminder_threshold_tokens,
        }

    queue_index = token_ids.index(token.id)
    current_serving_count = 1 if current_serving else 0
    people_ahead = current_serving_count + queue_index

    return {
        "queue_position": queue_index + 1,
        "tokens_away": queue_index,
        "people_ahead": people_ahead,
        "estimated_wait_minutes": people_ahead * token.department.average_service_time,
        "is_next": queue_index == 0,
        "current_serving_token_id": current_id,
        "current_serving_token_number": current_number,
        "reminder_threshold_tokens": token.department.reminder_threshold_tokens,
    }


def get_queue_summary(department_id: int, date=None) -> dict:
    if date is None:
        date = timezone.now().date()

    department = _get_department(department_id)
    current_serving = (
        PatientToken.objects.filter(
            department=department,
            date=date,
            status=TokenStatus.CALLED,
        )
        .select_related("patient", "counter")
        .order_by("called_at", "token_number")
        .first()
    )
    waiting_tokens = list(_ordered_waiting_queue(department, date))

    return {
        "department_id": department.id,
        "department_name": department.name,
        "date": date,
        "average_service_time": department.average_service_time,
        "reminder_threshold_tokens": department.reminder_threshold_tokens,
        "current_serving": current_serving,
        "up_next": waiting_tokens[0] if waiting_tokens else None,
        "waiting_count": len(waiting_tokens),
        "emergency_count": len([token for token in waiting_tokens if token.is_emergency]),
    }


def _notify_threshold_tokens(department: Department, date) -> None:
    threshold = department.reminder_threshold_tokens
    if threshold <= 0:
        return

    try:
        from notifications.models import NotificationLog, NotificationType
        from notifications.services import send_push_notification

        queued_tokens = list(_ordered_waiting_queue(department, date)[:threshold])
        for index, token in enumerate(queued_tokens):
            title = "You're Next" if index == 0 else "Queue Update"
            body = (
                f"Your token #{token.token_number} for {department.name} "
                f"is {index} token(s) away."
            )
            already_sent = NotificationLog.objects.filter(
                token=token,
                notification_type=NotificationType.TOKEN_REMINDER,
                title=title,
            ).exists()
            if not already_sent:
                send_push_notification(
                    user=token.patient,
                    title=title,
                    body=body,
                    notification_type=NotificationType.TOKEN_REMINDER,
                    token=token,
                )
    except Exception:
        pass


@transaction.atomic
def call_next_token(department_id: int, counter_id: int = None, complete_current: bool = True) -> PatientToken:
    department = _get_department(department_id)
    counter = _get_counter(counter_id, department) if counter_id else None
    today = timezone.now().date()
    now = timezone.now()

    current_tokens = list(
        PatientToken.objects.select_for_update().filter(
            department=department,
            date=today,
            status=TokenStatus.CALLED,
        )
    )
    if current_tokens and not complete_current:
        raise ServiceError("A token is already being served. Complete it before calling next.")

    for current in current_tokens:
        current.status = TokenStatus.COMPLETED
        current.completed_at = now
        current.save(update_fields=["status", "completed_at"])

    next_token = (
        PatientToken.objects.select_for_update()
        .filter(
            department=department,
            date=today,
            status__in=WAITING_QUEUE_STATUSES,
        )
        .order_by("-is_emergency", "token_number")
        .first()
    )
    if not next_token:
        raise ServiceError("No waiting tokens in queue.")

    next_token.status = TokenStatus.CALLED
    next_token.called_at = now
    update_fields = ["status", "called_at"]
    if counter:
        next_token.counter = counter
        update_fields.append("counter")
    next_token.save(update_fields=update_fields)

    refresh_queue_estimates(department, today)

    try:
        from notifications.services import notify_token_called
        notify_token_called(next_token)
    except Exception:
        pass

    _notify_threshold_tokens(department, today)
    next_token.refresh_from_db()
    return next_token


def _get_user_token(user, token_id: int) -> PatientToken:
    try:
        return PatientToken.objects.select_related("department", "counter").get(id=token_id, patient=user)
    except PatientToken.DoesNotExist:
        raise ServiceError("Token not found.")


def _get_token(token_id: int) -> PatientToken:
    try:
        return PatientToken.objects.select_related("department", "counter", "patient").get(id=token_id)
    except PatientToken.DoesNotExist:
        raise ServiceError("Token not found.")
