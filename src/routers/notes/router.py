import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from database.database_helper import AsyncDBSessionDep
from models.user import Note, Role, User
from routers.auth.dependencies import get_auth_user_from_access_token
from schemas.user import NoteCreate, NoteResponse

router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("/{patient_id}", response_model=NoteResponse)
async def add_note(
    patient_id: uuid.UUID,
    note_in: NoteCreate,
    current_user: Annotated[User, Depends(get_auth_user_from_access_token)],
    session: AsyncDBSessionDep,
):
    if current_user.role != Role.doctor:
        raise HTTPException(status_code=403, detail="Only doctors can add notes")

    note = Note(text=note_in.text, author_id=current_user.id, patient_id=patient_id)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


@router.get("/patient/{patient_id}", response_model=list[NoteResponse])
async def get_patient_notes(
    patient_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_auth_user_from_access_token)],
    session: AsyncDBSessionDep,
):
    if current_user.id != patient_id and current_user.role != Role.doctor:
        raise HTTPException(status_code=403, detail="Access denied")

    stmt = select(Note).where(Note.patient_id == patient_id)
    notes = (await session.execute(stmt)).scalars().all()
    return notes
