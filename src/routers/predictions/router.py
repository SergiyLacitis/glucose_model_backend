from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from schemas.glucose import (
    GlucoseReadingBatchCreate,
    GlucoseReadingCreate,
    GlucoseReadingResponse,
    PredictionPointResponse,
    PredictionResponse,
)
from sqlmodel import func, select

from database.database_helper import AsyncDBSessionDep
from models.user import GlucoseReading, Patient, Role, User
from routers.auth.dependencies import get_auth_user_from_access_token
from schemas.pagination import Page, PaginationParams, pagination_params
from services.predictor_service import PredictorService, get_predictor_service

router = APIRouter(prefix="/predictions", tags=["predictions"])

CurrentUserDep = Annotated[User, Depends(get_auth_user_from_access_token)]
PaginationDep = Annotated[PaginationParams, Depends(pagination_params)]
PredictorDep = Annotated[PredictorService, Depends(get_predictor_service)]


async def _ensure_can_access_patient(
    patient_id: uuid.UUID,
    current_user: User,
    session: AsyncDBSessionDep,
) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    if current_user.role == Role.admin:
        return patient
    if current_user.role == Role.patient and current_user.id == patient_id:
        return patient
    if current_user.role == Role.doctor and patient.doctor_id == current_user.id:
        return patient

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access to this patient is forbidden",
    )


@router.post(
    "/patients/{patient_id}/readings",
    response_model=GlucoseReadingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_reading(
    patient_id: uuid.UUID,
    payload: GlucoseReadingCreate,
    current_user: CurrentUserDep,
    session: AsyncDBSessionDep,
):
    await _ensure_can_access_patient(patient_id, current_user, session)

    reading = GlucoseReading(
        patient_id=patient_id,
        ts=payload.ts,
        glucose=payload.glucose,
        source=payload.source,
    )
    session.add(reading)
    await session.commit()
    await session.refresh(reading)
    return reading


@router.post(
    "/patients/{patient_id}/readings/batch",
    status_code=status.HTTP_201_CREATED,
)
async def add_readings_batch(
    patient_id: uuid.UUID,
    payload: GlucoseReadingBatchCreate,
    current_user: CurrentUserDep,
    session: AsyncDBSessionDep,
):
    await _ensure_can_access_patient(patient_id, current_user, session)

    if not payload.readings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Readings list is empty",
        )

    objs = [
        GlucoseReading(
            patient_id=patient_id,
            ts=r.ts,
            glucose=r.glucose,
            source=r.source,
        )
        for r in payload.readings
    ]
    session.add_all(objs)
    await session.commit()
    return {"inserted": len(objs)}


@router.get(
    "/patients/{patient_id}/readings",
    response_model=Page[GlucoseReadingResponse],
)
async def list_readings(
    patient_id: uuid.UUID,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    session: AsyncDBSessionDep,
):
    await _ensure_can_access_patient(patient_id, current_user, session)

    total_stmt = (
        select(func.count())
        .select_from(GlucoseReading)
        .where(GlucoseReading.patient_id == patient_id)
    )
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(GlucoseReading)
        .where(GlucoseReading.patient_id == patient_id)
        .order_by(GlucoseReading.ts.desc())  # type: ignore[attr-defined]
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    items = (await session.execute(stmt)).scalars().all()

    return Page[GlucoseReadingResponse](
        items=[
            GlucoseReadingResponse.model_validate(r, from_attributes=True)
            for r in items
        ],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


def _age_in_years(birth_date: date, at: date | None = None) -> float:
    if at is None:
        at = date.today()
    years = at.year - birth_date.year
    if (at.month, at.day) < (birth_date.month, birth_date.day):
        years -= 1
    return float(years)


@router.post(
    "/patients/{patient_id}/predict",
    response_model=PredictionResponse,
)
async def predict_glucose(
    patient_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: AsyncDBSessionDep,
    predictor_service: PredictorDep,
):
    if not predictor_service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=predictor_service.error or "Prediction model is unavailable",
        )

    patient = await _ensure_can_access_patient(patient_id, current_user, session)
    predictor = predictor_service.predictor

    history_minutes = max(predictor.required_history_minutes * 3, 6 * 60)
    cutoff = datetime.now(UTC) - timedelta(minutes=history_minutes)

    stmt = (
        select(GlucoseReading)
        .where(
            GlucoseReading.patient_id == patient_id,
            GlucoseReading.ts >= cutoff,
        )
        .order_by(GlucoseReading.ts.asc())  # type: ignore[attr-defined]
    )
    db_readings = (await session.execute(stmt)).scalars().all()

    if not db_readings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No measurements found in the last {history_minutes // 60} hours "
                f"for patient {patient_id}"
            ),
        )
    from glucose_predictor import GlucoseReading as PredReading
    from glucose_predictor import PatientInfo

    readings_for_model = [PredReading(ts=r.ts, glucose=r.glucose) for r in db_readings]

    sex_letter = "M" if patient.gender.value == "male" else "F"
    patient_info = PatientInfo(
        age=_age_in_years(patient.birth_date),
        sex=sex_letter,
    )

    try:
        result = predictor.predict(readings_for_model, patient_info)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    return PredictionResponse(
        patient_id=patient_id,
        horizon_min=result.horizon_min,
        last_observed_ts=result.last_observed_ts,
        last_observed_glucose=result.last_observed_glucose,
        predictions=[
            PredictionPointResponse(
                ts=p.ts, glucose=p.glucose, minutes_ahead=p.minutes_ahead
            )
            for p in result.predictions
        ],
    )
