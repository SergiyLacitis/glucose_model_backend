import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import func, select

from database.database_helper import AsyncDBSessionDep
from models.user import Note, Patient, Role, User
from routers.auth.dependencies import get_auth_user_from_access_token
from schemas.pagination import Page, PaginationParams, pagination_params
from schemas.user import NoteCreate, NoteResponse

router = APIRouter(prefix="/notes", tags=["notes"])

PaginationDep = Annotated[PaginationParams, Depends(pagination_params)]
CurrentUserDep = Annotated[User, Depends(get_auth_user_from_access_token)]


@router.post(
    "/{patient_id}",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_note(
    patient_id: uuid.UUID,
    note_in: NoteCreate,
    current_user: CurrentUserDep,
    session: AsyncDBSessionDep,
):
    if current_user.role != Role.doctor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can add notes",
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
            detail="You can only add notes to your own patients",
        )

    note = Note(text=note_in.text, author_id=current_user.id, patient_id=patient_id)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


@router.get("/patient/{patient_id}", response_model=Page[NoteResponse])
async def get_patient_notes(
    patient_id: uuid.UUID,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    session: AsyncDBSessionDep,
):
    if current_user.id != patient_id:
        if current_user.role != Role.doctor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
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
                detail="You can only read notes of your own patients",
            )

    total_stmt = (
        select(func.count()).select_from(Note).where(Note.patient_id == patient_id)
    )
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(Note)
        .where(Note.patient_id == patient_id)
        .order_by(Note.created_at.desc(), Note.id)  # type: ignore[arg-type]
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    notes = (await session.execute(stmt)).scalars().all()

    return Page[NoteResponse](
        items=[NoteResponse.model_validate(n, from_attributes=True) for n in notes],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )
