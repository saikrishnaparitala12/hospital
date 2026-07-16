from rest_framework import serializers
from .models import User, FCMToken, Role


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["phone", "full_name", "email", "password", "role"]

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Phone number already registered.")
        return value

    def validate_role(self, value):
        # ambulance role can only be assigned by admin via Django admin or direct DB — not via public register
        restricted = [Role.AMBULANCE, Role.ADMIN]
        if value in restricted:
            raise serializers.ValidationError(
                f"Role '{value}' cannot be self-registered. Contact the administrator."
            )
        return value


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)


class OTPRequestSerializer(serializers.Serializer):
    phone = serializers.CharField()


class OTPVerifySerializer(serializers.Serializer):
    phone = serializers.CharField()
    code = serializers.CharField(max_length=6)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "phone", "full_name", "email", "role", "is_phone_verified", "created_at"]
        read_only_fields = ["id", "created_at"]


class FCMTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = FCMToken
        fields = ["token", "device_type"]
