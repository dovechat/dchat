import logging
from typing import Annotated

import jwt
import redis.asyncio as redis

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db, get_db_read, get_db_write
from core.security import ALGORITHMS, SECRET_KEY
# from app.repositories.contact import ContactRepository
from repo.user import UserRepository
from schemas.auth_schemas import TokenPayload, UserContext
from services.auth_service import AuthService
from services.jwt_services import JWTService

log = logging.getLogger("uvicorn.error")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")


# Global redis instance
rdb = redis.from_url("redis://rdb:6379", decode_responses=True)

def get_jwt_service() -> JWTService:
    """Get JWT service instance."""
    return JWTService()


def get_auth_service(
    db: AsyncSession = Depends(get_db),
    jwt_service: JWTService = Depends(get_jwt_service),
) -> AuthService:
    """Get auth service instance."""
    return AuthService(jwt_service=jwt_service)

async def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    """Get user repository instance."""
    return UserRepository(db)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserContext:
    """Validate JWT token and return current user context."""
    print(f"\n\n\n *******************[DEBUG] get_current_user STARTED. Token: {token[:15]}...")
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHMS])
        token_data = TokenPayload(**payload)
    except InvalidTokenError as e:
        print(f"\n\n ******************* DEBUG: JWT Decode Error: {e}")
        raise credentials_exception

    if token_data.type != "access":
        raise credentials_exception
    log.info(f" /n/n --------------- token_data {token_data}  /n/n")
    user = await user_repo.get_by_id(token_data.sub)
    if not user:
        print(f"\n\n ******************* NOT FOUND IN DB: {token_data.sub} (type: {type(token_data.sub)})\n")
        raise credentials_exception

    return UserContext(
        id=user.id,
        email=user.email,
        role=token_data.role,
    )

# Annotated dependency for current user
CurrentUser = Annotated[UserContext, Depends(get_current_user)]
