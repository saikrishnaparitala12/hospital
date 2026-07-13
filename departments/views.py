from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from common.responses import success_response
from .models import Department, Counter, HospitalConfig
from .serializers import DepartmentSerializer, CounterSerializer, HospitalConfigSerializer


class DepartmentListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get(self, request):
        departments = Department.objects.filter(is_active=True).prefetch_related("counters")
        return success_response(DepartmentSerializer(departments, many=True).data)

    def post(self, request):
        serializer = DepartmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(serializer.data)


class DepartmentDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def _get_dept(self, pk):
        from common.exceptions import ServiceError
        try:
            return Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            raise ServiceError("Department not found.")

    def get(self, request, pk):
        return success_response(DepartmentSerializer(self._get_dept(pk)).data)

    def patch(self, request, pk):
        dept = self._get_dept(pk)
        serializer = DepartmentSerializer(dept, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(serializer.data)

    def delete(self, request, pk):
        self._get_dept(pk).delete()
        return success_response(message="Department deleted.")


class CounterListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get(self, request, dept_pk):
        counters = Counter.objects.filter(department_id=dept_pk, is_active=True)
        return success_response(CounterSerializer(counters, many=True).data)

    def post(self, request, dept_pk):
        serializer = CounterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(department_id=dept_pk)
        return success_response(serializer.data)


class HospitalConfigView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        return success_response(HospitalConfigSerializer(HospitalConfig.objects.all(), many=True).data)

    def post(self, request):
        serializer = HospitalConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(serializer.data)
