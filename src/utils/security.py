from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt

from config import settings


def _truncate_password(password: str) -> bytes:
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > settings.auth.bcrypt_max_bytes:
        pwd_bytes = pwd_bytes[: settings.auth.bcrypt_max_bytes]
    return pwd_bytes


def get_password_hash(password: str) -> str:
    pwd_bytes = _truncate_password(password)
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = _truncate_password(plain_password)
    hash_bytes = hashed_password.encode("utf-8")
    try:
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except ValueError:
        return False


def create_token(
    data: dict,
    token_type: Literal["access", "refresh"],
    expires_delta: timedelta,
) -> str:
    to_encode = data.copy()
    now = datetime.now(UTC)
    expire = now + expires_delta
    to_encode.update(
        {
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "type": token_type,
        }
    )

    encoded_jwt = jwt.encode(
        to_encode, settings.auth.secret_key, algorithm=settings.auth.algorithm
    )
    return encoded_jwt


def decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.auth.secret_key,
        algorithms=[settings.auth.algorithm],
        options={"require": ["exp", "sub", "type"]},
    )
