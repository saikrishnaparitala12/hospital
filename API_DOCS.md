# Hospital Token Management API — Documentation

## Project Setup

### Tech Stack
- **Backend**: Django 5.2 + Django REST Framework
- **Auth**: JWT via `djangorestframework-simplejwt`
- **Schema/Docs**: `drf-spectacular` (Swagger UI at `/api/docs/`)
- **Database**: PostgreSQL
- **Task Queue**: Celery + Redis
- **Notifications**: Firebase FCM (push) + AWS SNS (SMS)

### Environment Variables (`.env`)
```
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=hospital_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

CELERY_BROKER_URL=redis://localhost:6379/0

AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=<your_key>
AWS_SECRET_ACCESS_KEY=<your_secret>
```

### Local Setup
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy env file
cp .env.example .env   # then fill in values

# 3. Run migrations
python manage.py migrate

# 4. Create superuser
python manage.py createsuperuser

# 5. Start server
python manage.py runserver

# 6. Start Celery worker (separate terminal)
celery -A hospital worker -l info

# 7. Start Celery beat scheduler (separate terminal)
celery -A hospital beat -l info
```

### Interactive Swagger UI
```
GET /api/docs/        → Swagger UI
GET /api/schema/      → OpenAPI schema (YAML)
```

---

## Authentication

All protected endpoints require:
```
Authorization: Bearer <access_token>
```

JWT tokens:
- Access token lifetime: **1 hour**
- Refresh token lifetime: **7 days**
- Refresh tokens rotate on use

### User Roles
| Role | Description |
|------|-------------|
| `patient` | Default role, receives tokens and notifications on their phone |
| `doctor` | Hospital clinical staff |
| `token_admin` | Issues tokens on behalf of patients, sends reminders, completes/misses tokens |
| `admin` | Full access, staff/superuser |
| `ambulance` | Ambulance service operator. Assigned by admin only — cannot self-register. |

---

## Standard Response Format

### Success
```json
{
  "message": "Success",
  "data": { ... }
}
```

### Error
```json
{
  "message": "Error description"
}
```

---

## Notification Flow

### Automatic (Celery — no action needed from token_admin or patient)
| Trigger | Message sent to patient | Channel |
|---------|------------------------|---------|
| Token issued | "Your token #7 for Cardiology has been issued." | Push (FCM) + SMS (SNS) |
| 30 min before estimated time | "Your token #7 for Cardiology is coming up in ~30 minutes. Please be available." | Push (FCM) + SMS (SNS) |
| 1 hour after the 30-min reminder fires | Token auto-marked `completed` + "Your token #7 has been marked as completed. Thank you." | Push (FCM) + SMS (SNS) |

### Manual (Token Admin)
| How | What |
|-----|------|
| `POST /api/v1/tokens/<id>/send-reminder/` | Send a reminder for a specific token (Push + SMS) |
| `POST /api/v1/notifications/send/` | Send any custom message to any user (Push + optional SMS) |

### Daily Reset
`DailyTokenSequence` is keyed by `(department, date)` — every new day the token number automatically starts from 1 again. No manual action needed.

---

## Auth APIs — `/api/v1/auth/`

### POST `/api/v1/auth/register/`
Register a new user.

**Auth**: None

**Payload**
```json
{
  "phone": "9876543210",
  "full_name": "John Doe",
  "email": "john@example.com",
  "password": "secret123",
  "role": "patient"
}
```
> `role` options: `patient`, `doctor`, `token_admin`
> `ambulance` and `admin` roles cannot be self-registered — must be assigned by an administrator.

**Response** `201`
```json
{
  "message": "Registration successful.",
  "data": {
    "access": "<jwt_access_token>",
    "refresh": "<jwt_refresh_token>",
    "user": {
      "id": 1,
      "phone": "9876543210",
      "full_name": "John Doe",
      "role": "patient"
    }
  }
}
```

---

### POST `/api/v1/auth/login/`
Login with phone and password.

**Auth**: None

**Payload**
```json
{
  "phone": "9876543210",
  "password": "secret123"
}
```

**Response** `200`
```json
{
  "message": "Success",
  "data": {
    "access": "<jwt_access_token>",
    "refresh": "<jwt_refresh_token>",
    "user": {
      "id": 1,
      "phone": "9876543210",
      "full_name": "John Doe",
      "role": "patient"
    }
  }
}
```

---

### POST `/api/v1/auth/token/refresh/`
Refresh access token.

**Auth**: None

**Payload**
```json
{
  "refresh": "<jwt_refresh_token>"
}
```

**Response** `200`
```json
{
  "access": "<new_access_token>",
  "refresh": "<new_refresh_token>"
}
```

---

### POST `/api/v1/auth/otp/request/`
Send OTP to phone number via AWS SNS SMS.

**Auth**: None

**Payload**
```json
{
  "phone": "9876543210"
}
```

**Response** `200`
```json
{
  "message": "OTP sent successfully.",
  "data": null
}
```

---

### POST `/api/v1/auth/otp/verify/`
Verify OTP and mark phone as verified.

**Auth**: None

**Payload**
```json
{
  "phone": "9876543210",
  "code": "123456"
}
```

**Response** `200`
```json
{
  "message": "Phone verified successfully.",
  "data": {
    "access": "<jwt_access_token>",
    "refresh": "<jwt_refresh_token>"
  }
}
```

---

### GET `/api/v1/auth/me/`
Get current user profile.

**Auth**: Required

**Response** `200`
```json
{
  "message": "Success",
  "data": {
    "id": 1,
    "phone": "9876543210",
    "full_name": "John Doe",
    "email": "john@example.com",
    "role": "patient",
    "is_phone_verified": true,
    "created_at": "2025-01-01T10:00:00Z"
  }
}
```

---

### PATCH `/api/v1/auth/me/`
Update current user profile (partial update).

**Auth**: Required

**Payload** (all fields optional)
```json
{
  "full_name": "Jane Doe",
  "email": "jane@example.com"
}
```

**Response** `200` — same as GET `/me/`

---

### POST `/api/v1/auth/fcm-token/`
Register a device FCM token for push notifications.

**Auth**: Required

**Payload**
```json
{
  "token": "<fcm_device_token>",
  "device_type": "android"
}
```
> `device_type` options: `android`, `ios`, `web`

**Response** `200`
```json
{
  "message": "FCM token registered.",
  "data": null
}
```

---

### DELETE `/api/v1/auth/fcm-token/`
Remove a device FCM token.

**Auth**: Required

**Payload**
```json
{
  "token": "<fcm_device_token>"
}
```

**Response** `200`
```json
{
  "message": "FCM token removed.",
  "data": null
}
```

---

## Patient APIs — `/api/v1/patients/`

### GET `/api/v1/patients/profile/`
Get patient profile (auto-created if not exists).

**Auth**: Required

**Response** `200`
```json
{
  "message": "Success",
  "data": {
    "id": 1,
    "date_of_birth": "1990-05-15",
    "age": 35,
    "gender": "male",
    "blood_group": "O+",
    "profile_photo": "/media/photos/photo.jpg",
    "addresses": [],
    "emergency_contacts": [],
    "medical_id": null,
    "created_at": "2025-01-01T10:00:00Z"
  }
}
```
> `gender` options: `male`, `female`, `other`
> `blood_group` options: `A+`, `A-`, `B+`, `B-`, `AB+`, `AB-`, `O+`, `O-`

---

### PATCH `/api/v1/patients/profile/`
Update patient profile.

**Auth**: Required

**Payload** (all fields optional)
```json
{
  "date_of_birth": "1990-05-15",
  "gender": "male",
  "blood_group": "O+"
}
```

**Response** `200` — same as GET profile

---

### GET `/api/v1/patients/addresses/`
List all addresses for the patient.

**Auth**: Required

**Response** `200`
```json
{
  "message": "Success",
  "data": [
    {
      "id": 1,
      "line1": "123 Main St",
      "line2": "Apt 4B",
      "city": "Mumbai",
      "state": "Maharashtra",
      "pincode": "400001",
      "is_default": true
    }
  ]
}
```

---

### POST `/api/v1/patients/addresses/`
Add a new address.

**Auth**: Required

**Payload**
```json
{
  "line1": "123 Main St",
  "line2": "Apt 4B",
  "city": "Mumbai",
  "state": "Maharashtra",
  "pincode": "400001",
  "is_default": true
}
```

**Response** `200` — single address object

---

### PATCH `/api/v1/patients/addresses/<id>/`
Update an address.

**Auth**: Required

**Payload** (all fields optional)
```json
{
  "city": "Pune",
  "is_default": false
}
```

**Response** `200` — updated address object

---

### DELETE `/api/v1/patients/addresses/<id>/`
Delete an address.

**Auth**: Required

**Response** `200`
```json
{
  "message": "Address deleted.",
  "data": null
}
```

---

### GET `/api/v1/patients/emergency-contacts/`
List emergency contacts.

**Auth**: Required

**Response** `200`
```json
{
  "message": "Success",
  "data": [
    {
      "id": 1,
      "name": "Jane Doe",
      "relationship": "Spouse",
      "phone": "9876500000"
    }
  ]
}
```

---

### POST `/api/v1/patients/emergency-contacts/`
Add an emergency contact.

**Auth**: Required

**Payload**
```json
{
  "name": "Jane Doe",
  "relationship": "Spouse",
  "phone": "9876500000"
}
```

**Response** `200` — single contact object

---

### DELETE `/api/v1/patients/emergency-contacts/<id>/`
Delete an emergency contact.

**Auth**: Required

**Response** `200`
```json
{
  "message": "Emergency contact deleted.",
  "data": null
}
```

---

### GET `/api/v1/patients/medical-id/`
Get patient medical ID.

**Auth**: Required

**Response** `200`
```json
{
  "message": "Success",
  "data": {
    "id": 1,
    "allergies": "Penicillin",
    "chronic_conditions": "Diabetes Type 2",
    "current_medications": "Metformin 500mg",
    "notes": "Requires wheelchair access"
  }
}
```

---

### PATCH `/api/v1/patients/medical-id/`
Update medical ID.

**Auth**: Required

**Payload** (all fields optional)
```json
{
  "allergies": "Penicillin, Sulfa",
  "chronic_conditions": "Diabetes Type 2",
  "current_medications": "Metformin 500mg",
  "notes": "Requires wheelchair access"
}
```

**Response** `200` — updated medical ID object

---

## Department APIs — `/api/v1/`

### GET `/api/v1/departments/`
List all active departments with their counters.

**Auth**: Required

**Response** `200`
```json
{
  "message": "Success",
  "data": [
    {
      "id": 1,
      "name": "Cardiology",
      "description": "Heart and cardiovascular care",
      "is_active": true,
      "average_service_time": 15,
      "counters": [
        { "id": 1, "name": "Counter 1", "is_active": true }
      ]
    }
  ]
}
```
> `average_service_time` is in minutes, used for queue wait time estimation.

---

### POST `/api/v1/departments/`
Create a department.

**Auth**: Admin only

**Payload**
```json
{
  "name": "Cardiology",
  "description": "Heart and cardiovascular care",
  "is_active": true,
  "average_service_time": 15
}
```

**Response** `200` — created department object

---

### GET `/api/v1/departments/<id>/`
Get a single department.

**Auth**: Required

**Response** `200` — single department object

---

### PATCH `/api/v1/departments/<id>/`
Update a department.

**Auth**: Admin only

**Payload** (all fields optional)
```json
{
  "average_service_time": 20,
  "is_active": false
}
```

**Response** `200` — updated department object

---

### DELETE `/api/v1/departments/<id>/`
Delete a department.

**Auth**: Admin only

**Response** `200`
```json
{
  "message": "Department deleted.",
  "data": null
}
```

---

### GET `/api/v1/departments/<dept_id>/counters/`
List active counters for a department.

**Auth**: Required

**Response** `200`
```json
{
  "message": "Success",
  "data": [
    { "id": 1, "name": "Counter 1", "is_active": true }
  ]
}
```

---

### POST `/api/v1/departments/<dept_id>/counters/`
Add a counter to a department.

**Auth**: Admin only

**Payload**
```json
{
  "name": "Counter 2",
  "is_active": true
}
```

**Response** `200` — created counter object

---

## Token APIs — `/api/v1/tokens/`

### POST `/api/v1/tokens/issue/`
Token admin issues a queue token on behalf of a patient who has arrived at the hospital.

**Auth**: `token_admin` or `admin`

**Business Rules**:
- Token admin selects the department and records the patient's complaint (`issue_reason`)
- Only one active token per patient per department per day
- On issue: push notification + SMS sent to patient's phone automatically
- Celery schedules a 30-min reminder before the estimated time
- 1 hour after the 30-min reminder fires → token auto-completes + patient notified

**Payload**
```json
{
  "department_id": 1,
  "issue_reason": "Chest pain and shortness of breath"
}
```
> `issue_reason` is optional but recommended — records the patient's complaint/reason for visit.

**Response** `200`
```json
{
  "message": "Success",
  "data": {
    "id": 42,
    "token_number": 7,
    "date": "2025-01-15",
    "status": "waiting",
    "department": 1,
    "department_name": "Cardiology",
    "counter": null,
    "counter_name": null,
    "patient_phone": "9876543210",
    "estimated_time": "2025-01-15T11:30:00Z",
    "checked_in_at": null,
    "completed_at": null,
    "issue_reason": "Chest pain and shortness of breath",
    "notes": "",
    "created_at": "2025-01-15T10:00:00Z"
  }
}
```

**Token Status Values**
| Status | Description |
|--------|-------------|
| `waiting` | Token issued, patient in queue |
| `checked_in` | Patient has checked in at counter |
| `completed` | Service completed (manual or auto) |
| `cancelled` | Cancelled by patient |
| `missed` | Patient did not show up |

---

### GET `/api/v1/tokens/my/`
List all tokens for the current user (all dates, all statuses).

**Auth**: Required

**Response** `200`
```json
{
  "message": "Success",
  "data": [ { "...token object..." : "..." } ]
}
```

---

### GET `/api/v1/tokens/<id>/`
Get a specific token (must belong to current user).

**Auth**: Required

**Response** `200` — single token object

---

### POST `/api/v1/tokens/<id>/check-in/`
Patient checks in for their token (status must be `waiting`).

**Auth**: Required (token owner)

**Payload**: None

**Response** `200`
```json
{
  "message": "Checked in successfully.",
  "data": { "...token object with status": "checked_in" }
}
```

---

### POST `/api/v1/tokens/<id>/cancel/`
Patient cancels their token (status must be `waiting` or `checked_in`).

**Auth**: Required (token owner)

**Payload**: None

**Response** `200`
```json
{
  "message": "Token cancelled.",
  "data": { "...token object with status": "cancelled" }
}
```

---

### POST `/api/v1/tokens/<id>/send-reminder/`
Token admin manually sends a reminder notification to the patient for a specific token.

**Auth**: `token_admin` or `admin`

**Payload**: None

**What it does**:
- Sends FCM push notification to all patient devices
- Sends SMS via AWS SNS to patient's phone number

**Response** `200`
```json
{
  "message": "Reminder sent via push notification and SMS.",
  "data": {
    "token_id": 42,
    "token_number": 7,
    "patient_phone": "+919876543210"
  }
}
```

> Only works for tokens with status `waiting` or `checked_in`.
> Error `400` if token is already completed/cancelled/missed.

---

### POST `/api/v1/tokens/<id>/complete/`
Token admin manually marks a token as completed.

**Auth**: `token_admin` or `admin`

**Payload**: None

**Response** `200`
```json
{
  "message": "Token completed.",
  "data": { "...token object with status": "completed" }
}
```

---

### POST `/api/v1/tokens/<id>/missed/`
Token admin marks a token as missed (status must be `waiting`).

**Auth**: `token_admin` or `admin`

**Payload**: None

**Response** `200`
```json
{
  "message": "Token marked as missed.",
  "data": { "...token object with status": "missed" }
}
```

---

### GET `/api/v1/departments/<dept_id>/queue/`
Get the live queue for a department (waiting + checked_in tokens only).

**Auth**: Required

**Query Params**
| Param | Type | Description |
|-------|------|-------------|
| `date` | `YYYY-MM-DD` | Optional. Defaults to today |

**Example**: `GET /api/v1/departments/1/queue/?date=2025-01-15`

**Response** `200`
```json
{
  "message": "Success",
  "data": [
    {
      "id": 42,
      "token_number": 7,
      "status": "waiting",
      "patient_name": "John Doe",
      "patient_phone": "9876543210",
      "estimated_time": "2025-01-15T11:30:00Z",
      "checked_in_at": null
    }
  ]
}
```

---

## Notification APIs — `/api/v1/notifications/`

### GET `/api/v1/notifications/`
List notifications for the current user.

**Auth**: Required

**Query Params**
| Param | Value | Description |
|-------|-------|-------------|
| `unread` | `true` | Filter to unread only |

**Example**: `GET /api/v1/notifications/?unread=true`

**Response** `200`
```json
{
  "message": "Success",
  "data": [
    {
      "id": 1,
      "notification_type": "token_issued",
      "title": "Token Issued",
      "body": "Your token #7 for Cardiology has been issued.",
      "is_read": false,
      "sent_at": "2025-01-15T10:00:00Z"
    }
  ]
}
```

**Notification Type Values**
| Type | When |
|------|------|
| `token_issued` | Token created |
| `token_reminder` | 30-min reminder (auto or manual) |
| `token_completed` | Token auto-completed after 1 hour |
| `token_called` | Token called to counter |
| `token_cancelled` | Token cancelled |
| `token_missed` | Token marked missed |
| `general` | Admin manual send |

---

### POST `/api/v1/notifications/mark-all-read/`
Mark all notifications as read.

**Auth**: Required

**Payload**: None

**Response** `200`
```json
{
  "message": "All notifications marked as read.",
  "data": null
}
```

---

### POST `/api/v1/notifications/<id>/read/`
Mark a single notification as read.

**Auth**: Required

**Payload**: None

**Response** `200`
```json
{
  "message": "Notification marked as read.",
  "data": null
}
```

---

### POST `/api/v1/notifications/send/`
Admin manually sends a custom notification to any user (push + optional SMS).

**Auth**: Admin only

**Payload**
```json
{
  "user_id": 1,
  "title": "Appointment Reminder",
  "body": "Your appointment is in 30 minutes.",
  "send_sms": true,
  "token_id": 42
}
```
> `send_sms`: optional, default `false`. Sends SMS via AWS SNS.
> `token_id`: optional, links notification to a specific token.

**Response** `200`
```json
{
  "message": "Notification sent.",
  "data": {
    "id": 10,
    "notification_type": "general",
    "title": "Appointment Reminder",
    "body": "Your appointment is in 30 minutes.",
    "is_read": false,
    "sent_at": "2025-01-15T10:05:00Z"
  }
}
```

---

## Error Responses

### 400 Bad Request
```json
{ "message": "You already have an active token for this department today." }
```

### 401 Unauthorized
```json
{ "detail": "Authentication credentials were not provided." }
```

### 403 Forbidden
```json
{ "detail": "You do not have permission to perform this action." }
```

### 404 / Service Error
```json
{ "message": "Token not found." }
```

### 422 Validation Error
```json
{
  "phone": ["Phone number already registered."],
  "password": ["This field is required."]
}
```

---

## API Summary Table

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/register/` | None | Register user |
| POST | `/api/v1/auth/login/` | None | Login, get JWT |
| POST | `/api/v1/auth/token/refresh/` | None | Refresh JWT |
| POST | `/api/v1/auth/otp/request/` | None | Send OTP via SMS |
| POST | `/api/v1/auth/otp/verify/` | None | Verify OTP |
| GET | `/api/v1/auth/me/` | Required | Get own profile |
| PATCH | `/api/v1/auth/me/` | Required | Update own profile |
| POST | `/api/v1/auth/fcm-token/` | Required | Register FCM token |
| DELETE | `/api/v1/auth/fcm-token/` | Required | Remove FCM token |
| GET | `/api/v1/patients/profile/` | Required | Get patient profile |
| PATCH | `/api/v1/patients/profile/` | Required | Update patient profile |
| GET | `/api/v1/patients/addresses/` | Required | List addresses |
| POST | `/api/v1/patients/addresses/` | Required | Add address |
| PATCH | `/api/v1/patients/addresses/<id>/` | Required | Update address |
| DELETE | `/api/v1/patients/addresses/<id>/` | Required | Delete address |
| GET | `/api/v1/patients/emergency-contacts/` | Required | List emergency contacts |
| POST | `/api/v1/patients/emergency-contacts/` | Required | Add emergency contact |
| DELETE | `/api/v1/patients/emergency-contacts/<id>/` | Required | Delete emergency contact |
| GET | `/api/v1/patients/medical-id/` | Required | Get medical ID |
| PATCH | `/api/v1/patients/medical-id/` | Required | Update medical ID |
| GET | `/api/v1/departments/` | Required | List departments |
| POST | `/api/v1/departments/` | Admin | Create department |
| GET | `/api/v1/departments/<id>/` | Required | Get department |
| PATCH | `/api/v1/departments/<id>/` | Admin | Update department |
| DELETE | `/api/v1/departments/<id>/` | Admin | Delete department |
| GET | `/api/v1/departments/<id>/counters/` | Required | List counters |
| POST | `/api/v1/departments/<id>/counters/` | Admin | Add counter |
| POST | `/api/v1/tokens/issue/` | token_admin / admin | Issue token for patient |
| GET | `/api/v1/tokens/my/` | Required | My tokens |
| GET | `/api/v1/tokens/<id>/` | Required | Token detail |
| POST | `/api/v1/tokens/<id>/check-in/` | Required | Patient checks in |
| POST | `/api/v1/tokens/<id>/cancel/` | Required | Patient cancels token |
| POST | `/api/v1/tokens/<id>/send-reminder/` | token_admin / admin | Manual reminder (Push + SMS) |
| POST | `/api/v1/tokens/<id>/complete/` | token_admin / admin | Complete token |
| POST | `/api/v1/tokens/<id>/missed/` | token_admin / admin | Mark token missed |
| GET | `/api/v1/departments/<id>/queue/` | Required | Live queue |
| GET | `/api/v1/notifications/` | Required | List notifications |
| POST | `/api/v1/notifications/mark-all-read/` | Required | Mark all read |
| POST | `/api/v1/notifications/<id>/read/` | Required | Mark one read |
| POST | `/api/v1/notifications/send/` | Admin | Custom notification send |
