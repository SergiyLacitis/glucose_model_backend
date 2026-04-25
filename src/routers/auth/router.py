from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from config import settings
from database.database_helper import AsyncDBSessionDep
from models.user import Doctor, Patient, Role, User
from schemas.token import Token
from schemas.user import DoctorRegister, PatientCreate, UserResponse
from utils.security import create_token, get_password_hash

from .dependencies import (
    get_auth_user_from_access_token,
    get_auth_user_from_refresh_token,
    validate_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def generate_token_info(user: User) -> Token:
    common_claims = {"sub": user.email, "uid": str(user.id)}

    access_token = create_token(
        data=common_claims,
        token_type="access",
        expires_delta=timedelta(minutes=settings.auth.access_token_expire_minutes),
    )
    refresh_token = create_token(
        data=common_claims,
        token_type="refresh",
        expires_delta=timedelta(days=settings.auth.refresh_token_expire_days),
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/login", response_model=Token)
async def login(user: Annotated[User, Depends(validate_user)]):
    return generate_token_info(user)


@router.post(
    "/register",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
)
async def register_doctor(user_in: DoctorRegister, session: AsyncDBSessionDep):
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        role=Role.doctor,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        ) from err

    doctor = Doctor(
        id=user.id,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        middle_name=user_in.middle_name,
        birth_date=user_in.birth_date,
        gender=user_in.gender,
    )
    session.add(doctor)

    try:
        await session.commit()
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create doctor profile",
        ) from err

    return generate_token_info(user)


@router.post("/register-patient", status_code=status.HTTP_201_CREATED)
async def register_patient(
    patient_in: PatientCreate,
    current_user: Annotated[User, Depends(get_auth_user_from_access_token)],
    session: AsyncDBSessionDep,
):
    if current_user.role != Role.doctor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can register patients",
        )

    doctor_profile = await session.get(Doctor, current_user.id)
    if doctor_profile is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctor profile not found",
        )

    user = User(
        email=patient_in.email,
        hashed_password=get_password_hash(patient_in.password),
        role=Role.patient,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        ) from err

    patient = Patient(
        id=user.id,
        first_name=patient_in.first_name,
        last_name=patient_in.last_name,
        middle_name=patient_in.middle_name,
        birth_date=patient_in.birth_date,
        gender=patient_in.gender,
        doctor_id=current_user.id,
    )
    session.add(patient)

    try:
        await session.commit()
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create patient profile",
        ) from err

    return {"status": "success", "patient_id": user.id}


@router.post("/refresh", response_model=Token)
async def refresh_token(
    user: Annotated[User, Depends(get_auth_user_from_refresh_token)],
):
    return generate_token_info(user)


@router.get("/users/me", response_model=UserResponse)
async def get_me(
    user: Annotated[User, Depends(get_auth_user_from_access_token)],
):
    return user
