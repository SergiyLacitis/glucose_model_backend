import enum
import uuid
from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, Relationship, SQLModel


class Role(enum.StrEnum):
    patient = "patient"
    doctor = "doctor"
    admin = "admin"


class Gender(enum.StrEnum):
    male = "male"
    female = "female"


class User(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    role: Role
    is_active: bool = Field(default=True)

    doctor_profile: Optional["Doctor"] = Relationship(back_populates="user")
    patient_profile: Optional["Patient"] = Relationship(back_populates="user")


class Doctor(SQLModel, table=True):
    id: uuid.UUID = Field(primary_key=True, foreign_key="user.id")
    first_name: str
    last_name: str
    middle_name: str | None = None
    birth_date: date
    gender: Gender

    user: User = Relationship(back_populates="doctor_profile")
    patients: list["Patient"] = Relationship(back_populates="doctor")
    notes: list["Note"] = Relationship(back_populates="author")


class Patient(SQLModel, table=True):
    id: uuid.UUID = Field(primary_key=True, foreign_key="user.id")
    first_name: str
    last_name: str
    middle_name: str | None = None
    birth_date: date
    gender: Gender

    doctor_id: uuid.UUID = Field(foreign_key="doctor.id", index=True)

    user: User = Relationship(back_populates="patient_profile")
    doctor: Doctor = Relationship(back_populates="patients")
    notes: list["Note"] = Relationship(back_populates="patient")


class Note(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    text: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    author_id: uuid.UUID = Field(foreign_key="doctor.id", index=True)
    patient_id: uuid.UUID = Field(foreign_key="patient.id", index=True)

    author: Doctor = Relationship(back_populates="notes")
    patient: Patient = Relationship(back_populates="notes")
