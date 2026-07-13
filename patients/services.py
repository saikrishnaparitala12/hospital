from common.exceptions import ServiceError
from .models import Patient, Address, EmergencyContact, MedicalID


def get_or_create_patient(user) -> Patient:
    patient, _ = Patient.objects.get_or_create(user=user)
    return patient


def update_patient(user, data: dict) -> Patient:
    patient = get_or_create_patient(user)
    for field, value in data.items():
        setattr(patient, field, value)
    patient.save()
    return patient


def add_address(user, data: dict) -> Address:
    patient = get_or_create_patient(user)
    if data.get("is_default"):
        patient.addresses.filter(is_default=True).update(is_default=False)
    return Address.objects.create(patient=patient, **data)


def update_address(user, address_id: int, data: dict) -> Address:
    patient = get_or_create_patient(user)
    try:
        address = patient.addresses.get(id=address_id)
    except Address.DoesNotExist:
        raise ServiceError("Address not found.")
    if data.get("is_default"):
        patient.addresses.filter(is_default=True).update(is_default=False)
    for field, value in data.items():
        setattr(address, field, value)
    address.save()
    return address


def delete_address(user, address_id: int) -> None:
    patient = get_or_create_patient(user)
    patient.addresses.filter(id=address_id).delete()


def add_emergency_contact(user, data: dict) -> EmergencyContact:
    patient = get_or_create_patient(user)
    return EmergencyContact.objects.create(patient=patient, **data)


def delete_emergency_contact(user, contact_id: int) -> None:
    patient = get_or_create_patient(user)
    patient.emergency_contacts.filter(id=contact_id).delete()


def upsert_medical_id(user, data: dict) -> MedicalID:
    patient = get_or_create_patient(user)
    medical_id, _ = MedicalID.objects.get_or_create(patient=patient)
    for field, value in data.items():
        setattr(medical_id, field, value)
    medical_id.save()
    return medical_id
