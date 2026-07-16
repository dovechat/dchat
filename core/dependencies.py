import logging
from typing import Annotated
import json
import jwt
import redis.asyncio as redis

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db, get_db_read, get_db_write
from core.redis import rdb
from core.security import ALGORITHMS, SECRET_KEY
# from app.repositories.contact import ContactRepository
from repo.user import UserRepository
from repo.tenant_repo import TenantRepository
from repo.line_repo import LineRepository
from schemas.auth_schemas import TokenPayload, UserContext
from services.auth_service import AuthService
from services.jwt_services import JWTService
from services.line_service import LineService
from services.user_service import UserService

log = logging.getLogger("uvicorn.error")

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"http://0.0.0.0:8071/api/v1/auth/login")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Global redis instance
# rdb = redis.from_url("redis://redis:6379", decode_responses=True)

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
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHMS])
        token_data = TokenPayload(**payload)
    except InvalidTokenError:
        raise credentials_exception

    if token_data.type != "access":
        raise credentials_exception

    cache_key = f"user:{token_data.sub}"

    cached_user = await rdb.get(cache_key)

    if cached_user:
        user_data = json.loads(cached_user)
    else:
        user = await user_repo.get_by_id(token_data.sub)

        if not user:
            raise credentials_exception

        user_data = {
            "id": str(user.id),
            "email": user.email,
        }

        await rdb.setex(
            cache_key,
            300,
            json.dumps(user_data),
        )

    return UserContext(
        id=user_data["id"],
        email=user_data["email"],
        role=token_data.role,
        member=token_data.member,
        tenant_id=token_data.tenant_id,
    )

# ------- tenants
async def get_tenant_repo(db: AsyncSession = Depends(get_db)) -> TenantRepository:
    """Get tenant repository instance."""
    return TenantRepository(db)

# ------- lines
async def get_line_repo(db: AsyncSession = Depends(get_db)) -> LineRepository:
    return LineRepository(db)

async def get_line_service(
    line_repo: LineRepository = Depends(get_line_repo),
) -> LineService:
    return LineService(line_repo)

# ------ users
def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserService:
    from services.user_service import UserService
    return UserService(user_repo)