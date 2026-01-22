import random
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.redis import rdb
from models.tenants import UserStatus
from repo.user import UserRepository
from schemas.auth_schemas import LoginRequest, RegisterRequest, TokenPair, UserContext as User
from services.jwt_services import JWTService

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


async def is_throttled(key: str, seconds: int) -> bool:
    """
    Check if the action is throttled using atomic SET NX.
    Returns True if throttled, False if allowed.
    """
    res = await rdb.set(f"throttle:{key}", "1", ex=seconds, nx=True)

    # Handle various return types from different redis-py versions
    if res in [True, "OK", 1]:
        return False

    return True


class AuthService:
    """Service for authentication operations"""

    def __init__(self, jwt_service: JWTService) -> None:
        self.jwt_service = jwt_service

    async def login(
        self,
        request: LoginRequest,
        db: AsyncSession,
        organization_id: int | None = None,
    ) -> TokenPair:
        """User login"""
        user_repo = UserRepository(db)
        user = await user_repo.get_by_email(request.email)
        if not user or not self.jwt_service.verify_password(
            request.password, user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        role = None
        return self.jwt_service.create_token_pair(
            user_id=user.id, role=role
        )

    async def register(
        self,
        data: RegisterRequest,
        db: AsyncSession,
    ) -> TokenPair:
        """Full registration: user + organization + owner"""
        user_repo = UserRepository(db)

        existing = await user_repo.get_by_email(data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists",
            )
        log.info(f"\n\n ************* AuthService.register_user data {data} \n\n")
        data.password = self.jwt_service.password_hash(data.password)

        user = await user_repo.create_user(data)

        # Generate 4-digit code
        code = f"{random.randint(0, 9999):04d}"
        log.info(f"VERIFICATION CODE FOR {data.email}: {code}")

        await rdb.setex(f"auth:{str(user.id)}", 600, code)

        return self.jwt_service.create_token_pair(
            user_id=user.id,
            role="owner",
        )

    async def verify_code(self, user_id: str, code: str, db: AsyncSession) -> str:
        lock_key = f"activated_lock:{user_id}"

        # 1. Throttle check
        is_locked = await rdb.get(lock_key)
        log.info(f"AUTH_VERIFY: user={user_id} is_locked={is_locked is not None}")

        if is_locked:
            log.warning(f"AUTH_VERIFY: too_fast for user={user_id}")
            return "too_fast"

        # Set 3s lock immediately
        await rdb.set(lock_key, "1", ex=3)
        log.info(f"AUTH_VERIFY: lock set for user={user_id}")

        # 2. Status check
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        if not user:
            log.error(f"AUTH_VERIFY: user_not_found {user_id}")
            return "user_not_found"

        if user.status in [UserStatus.trial, UserStatus.active]:
            log.info(f"AUTH_VERIFY: already_activated user={user_id}")
            return "already_activated"

        # 3. Code validation
        stored_code = await rdb.get(f"auth:{user_id}")
        log.info(f"AUTH_VERIFY: provided={code} stored={stored_code}")

        if not stored_code or stored_code != code:
            log.info(f"AUTH_VERIFY: invalid_code for user={user_id}")
            return "invalid_code"

        # 4. Success flow
        user.status = UserStatus.trial
        await user_repo.update(user)
        await rdb.delete(f"auth:{user_id}")
        log.info(f"AUTH_VERIFY: ok for user={user_id}")

        return "ok"