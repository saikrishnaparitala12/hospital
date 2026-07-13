from rest_framework.response import Response
from rest_framework import status


def success_response(data=None, message="Success", status_code=status.HTTP_200_OK):
    return Response({"message": message, "data": data}, status=status_code)


def error_response(message="Error", status_code=status.HTTP_400_BAD_REQUEST):
    return Response({"message": message}, status=status_code)
