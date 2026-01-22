from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from core.config import settings

SECRET_KEY = settings.secret_key
ALGORITHMS = settings.algorithm


def get_password_hash(password: str) -> str:
    """Hash password using bcrypt."""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def create_access_token(
    subject: int,
    organization_id: int | None = None,
    role: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create JWT access token."""
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "type": "access",
    }
    if organization_id is not None:
        to_encode["organization_id"] = organization_id
    if role is not None:
        to_encode["role"] = role
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHMS)


def create_refresh_token(
    subject: int,
    organization_id: int | None = None,
    role: str | None = None,
) -> str:
    """Create JWT refresh token."""
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
    }
    if organization_id is not None:
        to_encode["organization_id"] = organization_id
    if role is not None:
        to_encode["role"] = role
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHMS)
