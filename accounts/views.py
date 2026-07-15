from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework_simplejwt.views import TokenRefreshView

from common.responses import success_response, error_response
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    UserSerializer,
    FCMTokenSerializer,
)
from . import services


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = services.register_user(serializer.validated_data)
        return success_response(
            data,
            message="Registration successful.",
            status_code=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = services.login_user(
            serializer.validated_data["phone"],
            serializer.validated_data["password"],
        )
        return success_response(data)


class OTPRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.send_otp(serializer.validated_data["phone"])
        return success_response(message="OTP sent successfully.")


class OTPVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = services.verify_otp(
            serializer.validated_data["phone"],
            serializer.validated_data["code"],
        )
        return success_response(data, message="Phone verified successfully.")


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return success_response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(serializer.data)


class FCMTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FCMTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.register_fcm_token(
            request.user,
            serializer.validated_data["token"],
            serializer.validated_data.get("device_type", ""),
        )
        return success_response(message="FCM token registered.")

    def delete(self, request):
        token = request.data.get("token")
        if not token:
            return error_response("Token is required.")
        services.remove_fcm_token(request.user, token)
        return success_response(message="FCM token removed.")
