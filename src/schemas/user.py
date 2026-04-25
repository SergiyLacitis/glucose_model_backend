import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr

from models.user import Gender, Role


class NoteCreate(BaseModel):
    text: str


class NoteResponse(BaseModel):
    id: uuid.UUID
    text: str
    created_at: datetime
    author_id: uuid.UUID
    patient_id: uuid.UUID


class DoctorRegister(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    middle_name: str | None = None
    birth_date: date
    gender: Gender


class PatientCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    middle_name: str | None = None
    birth_date: date
    gender: Gender


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: Role


class DoctorResponse(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    middle_name: str | None = None
    birth_date: date
    gender: Gender


class PatientResponse(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    middle_name: str | None = None
    birth_date: date
    gender: Gender
    doctor_id: uuid.UUID


class PatientTransferRequest(BaseModel):
    new_doctor_id: uuid.UUID
