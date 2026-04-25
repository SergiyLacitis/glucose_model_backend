from fastapi import APIRouter

from .auth import auth_router
from .doctors import doctors_router
from .notes import notes_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(notes_router)
api_router.include_router(doctors_router)
