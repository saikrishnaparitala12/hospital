from django.utils import timezone
from datetime import timedelta
from rest_framework_simplejwt.tokens import RefreshToken
from common.exceptions import ServiceError
from .models import User, OTP, FCMToken


def register_user(validated_data: dict) -> User:
    password = validated_data.pop("password")
    user = User(**validated_data)
    user.set_password(password)
    user.save()
    return user


def login_user(phone: str, password: str) -> dict:
    try:
        user = User.objects.get(phone=phone)
    except User.DoesNotExist:
        raise ServiceError("Invalid phone or password.")

    if not user.check_password(password):
        raise ServiceError("Invalid phone or password.")

    if not user.is_active:
        raise ServiceError("Account is disabled.")

    return _get_tokens(user)


def _get_tokens(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "user": {
            "id": user.id,
            "phone": user.phone,
            "full_name": user.full_name,
            "role": user.role,
        },
    }


def send_otp(phone: str) -> None:
    try:
        user = User.objects.get(phone=phone)
    except User.DoesNotExist:
        raise ServiceError("User not found.")

    # Invalidate previous unused OTPs
    OTP.objects.filter(user=user, is_used=False).update(is_used=True)

    code = OTP.generate_code()
    OTP.objects.create(
        user=user,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    # TODO: integrate SMS gateway here
    # sms_service.send(phone, f"Your OTP is {code}")


def verify_otp(phone: str, code: str) -> dict:
    try:
        user = User.objects.get(phone=phone)
    except User.DoesNotExist:
        raise ServiceError("User not found.")

    otp = (
        OTP.objects.filter(user=user, code=code, is_used=False)
        .order_by("-created_at")
        .first()
    )

    if not otp:
        raise ServiceError("Invalid OTP.")

    if otp.expires_at < timezone.now():
        raise ServiceError("OTP has expired.")

    otp.is_used = True
    otp.save(update_fields=["is_used"])

    user.is_phone_verified = True
    user.save(update_fields=["is_phone_verified"])

    return _get_tokens(user)


def register_fcm_token(user: User, token: str, device_type: str = "") -> FCMToken:
    obj, _ = FCMToken.objects.update_or_create(
        token=token,
        defaults={"user": user, "device_type": device_type},
    )
    return obj


def remove_fcm_token(user: User, token: str) -> None:
    FCMToken.objects.filter(user=user, token=token).delete()
