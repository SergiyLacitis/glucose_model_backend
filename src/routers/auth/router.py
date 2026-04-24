from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from config import settings
from database.database_helper import AsyncDBSessionDep
from models.user import User
from schemas.token import Token
from schemas.user import UserCreate, UserResponse
from utils.security import create_token, get_password_hash

from .dependencies import (
    get_auth_user_from_access_token,
    get_auth_user_from_refresh_token,
    validate_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def generate_token_info(user: User) -> Token:
    access_token = create_token(
        data={"sub": user.email},
        token_type="access",
        expires_delta=timedelta(minutes=settings.auth.access_token_expire_minutes),
    )
    refresh_token = create_token(
        data={"sub": user.email},
        token_type="refresh",
        expires_delta=timedelta(days=settings.auth.refresh_token_expire_days),
    )
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=Token)
async def login(user: Annotated[User, Depends(validate_user)]):
    return generate_token_info(user)


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, session: AsyncDBSessionDep):
    stmt = select(User).where(User.email == user_in.email)
    existing_user = (await session.execute(stmt)).scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return generate_token_info(user)


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
