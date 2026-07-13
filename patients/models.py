from django.db import models
from accounts.models import User
from common.models import BaseModel
from common.choices import BloodGroup, Gender


class Patient(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="patient_profile")
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    blood_group = models.CharField(max_length=5, choices=BloodGroup.choices, blank=True)
    profile_photo = models.ImageField(upload_to="patients/photos/", null=True, blank=True)

    def __str__(self):
        return f"Patient({self.user.phone})"

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        from django.utils import timezone
        today = timezone.now().date()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class Address(BaseModel):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="addresses")
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.line1}, {self.city}"


class EmergencyContact(BaseModel):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="emergency_contacts")
    name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=50)
    phone = models.CharField(max_length=15)

    def __str__(self):
        return f"{self.name} ({self.relationship})"


class MedicalID(BaseModel):
    patient = models.OneToOneField(Patient, on_delete=models.CASCADE, related_name="medical_id")
    allergies = models.TextField(blank=True)
    chronic_conditions = models.TextField(blank=True)
    current_medications = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"MedicalID({self.patient.user.phone})"
