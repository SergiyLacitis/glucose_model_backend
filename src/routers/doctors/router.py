import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import func, select

from database.database_helper import AsyncDBSessionDep
from models.user import Doctor, Patient, Role, User
from routers.auth.dependencies import get_auth_user_from_access_token
from schemas.pagination import Page, PaginationParams, pagination_params
from schemas.user import DoctorResponse, PatientResponse, PatientTransferRequest

router = APIRouter(prefix="/doctors", tags=["doctors"])

PaginationDep = Annotated[PaginationParams, Depends(pagination_params)]
CurrentUserDep = Annotated[User, Depends(get_auth_user_from_access_token)]


def _ensure_doctor(user: User) -> None:
    if user.role != Role.doctor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can access this resource",
        )


@router.get("", response_model=Page[DoctorResponse])
async def list_doctors(
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    session: AsyncDBSessionDep,
):
    _ensure_doctor(current_user)
    total_stmt = select(func.count()).select_from(Doctor)
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(Doctor)
        .order_by(Doctor.last_name, Doctor.first_name, Doctor.id)  # type: ignore[arg-type]
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    doctors = (await session.execute(stmt)).scalars().all()

    return Page[DoctorResponse](
        items=[DoctorResponse.model_validate(d, from_attributes=True) for d in doctors],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/me/patients", response_model=Page[PatientResponse])
async def list_my_patients(
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    session: AsyncDBSessionDep,
):
    _ensure_doctor(current_user)

    total_stmt = (
        select(func.count())
        .select_from(Patient)
        .where(Patient.doctor_id == current_user.id)
    )
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(Patient)
        .where(Patient.doctor_id == current_user.id)
        .order_by(Patient.last_name, Patient.first_name, Patient.id)  # type: ignore[arg-type]
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    patients = (await session.execute(stmt)).scalars().all()

    return Page[PatientResponse](
        items=[
            PatientResponse.model_validate(p, from_attributes=True) for p in patients
        ],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "/me/patients/{patient_id}/transfer",
    response_model=PatientResponse,
)
async def transfer_patient(
    patient_id: uuid.UUID,
    body: PatientTransferRequest,
    current_user: CurrentUserDep,
    session: AsyncDBSessionDep,
):
    _ensure_doctor(current_user)

    if body.new_doctor_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Patient is already assigned to you",
        )

    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )
    if patient.doctor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only transfer your own patients",
        )

    new_doctor = await session.get(Doctor, body.new_doctor_id)
    if new_doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target doctor not found",
        )

    patient.doctor_id = body.new_doctor_id
    session.add(patient)
    await session.commit()
    await session.refresh(patient)

    return PatientResponse.model_validate(patient, from_attributes=True)
