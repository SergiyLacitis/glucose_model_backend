from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from sqlmodel import select

from database.database_helper import AsyncDBSessionDep
from models.user import User
from utils import security

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def validate_user(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: AsyncDBSessionDep,
) -> User:
    stmt = select(User).where(User.email == form_data.username)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if not user or not security.verify_password(
        form_data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_payload(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> dict:
    try:
        return security.decode_token(token)
    except ExpiredSignatureError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from err
    except InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from err


async def _get_auth_user_from_token(
    payload: dict,
    session: AsyncDBSessionDep,
    expected_type: str,
) -> User:
    token_type = payload.get("type")
    if token_type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type: expected '{expected_type}'",
        )

    email = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    stmt = select(User).where(User.email == email)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is disabled",
        )

    return user


async def get_auth_user_from_access_token(
    payload: Annotated[dict, Depends(get_current_user_payload)],
    session: AsyncDBSessionDep,
) -> User:
    return await _get_auth_user_from_token(payload, session, "access")


async def get_auth_user_from_refresh_token(
    payload: Annotated[dict, Depends(get_current_user_payload)],
    session: AsyncDBSessionDep,
) -> User:
    return await _get_auth_user_from_token(payload, session, "refresh")
