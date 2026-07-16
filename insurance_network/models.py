from django.db import models
from common.models import BaseModel


class InsuranceCompany(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    website = models.URLField(blank=True)
    logo_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    last_scraped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Insurance Companies"

    def __str__(self):
        return self.name


class Hospital(BaseModel):
    name = models.CharField(max_length=512)
    normalized_name = models.CharField(max_length=512, db_index=True)
    address = models.TextField()
    normalized_address = models.TextField()
    city = models.CharField(max_length=255, db_index=True)
    state = models.CharField(max_length=255, db_index=True)
    pincode = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geocoded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("normalized_name", "pincode")]
        indexes = [models.Index(fields=["latitude", "longitude"], name="hospital_geo_idx")]

    def __str__(self):
        return f"{self.name} — {self.city}"


class InsuranceHospitalNetwork(BaseModel):
    insurance = models.ForeignKey(
        InsuranceCompany, on_delete=models.CASCADE, related_name="hospital_networks"
    )
    hospital = models.ForeignKey(
        Hospital, on_delete=models.CASCADE, related_name="insurance_networks"
    )
    plan_types = models.JSONField(default=list, blank=True)  # e.g. ["cashless", "reimbursement"]
    is_active = models.BooleanField(default=True)
    source_url = models.URLField(blank=True)

    class Meta:
        unique_together = [("insurance", "hospital")]

    def __str__(self):
        return f"{self.insurance.name} ↔ {self.hospital.name}"


class ScrapeLog(BaseModel):
    insurance = models.ForeignKey(
        InsuranceCompany, on_delete=models.CASCADE, related_name="scrape_logs"
    )
    status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("running", "Running"), ("success", "Success"), ("failed", "Failed")],
        default="pending",
    )
    hospitals_found = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.insurance.name} scrape — {self.status}"
