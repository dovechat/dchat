import uuid

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException

from core.config import settings
from schemas.auth_schemas import TokenPayload, TokenType

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


class JWTService:
    """JWT token and password service."""

    def __init__(self) -> None:
        self.secret_key = settings.secret_key
        self.algorithm = settings.algorithm
        self.access_expires = timedelta(minutes=settings.access_token_expire_minutes)
        self.refresh_expires = timedelta(days=settings.refresh_token_expire_days)

    def password_hash(self, password: str) -> str:
        """Hash password using bcrypt"""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")



    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        log.info(f"\n\n ************* plain_password {plain_password} hashed_password {hashed_password}")
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )

    def _create_token(
            self,
            user_id: int,
            token_type: TokenType,
            role: str | None = None,
            tenant_id: str | uuid.UUID | None = None,
    ) -> str:
        """Create a single JWT token"""
        log.info(f"\n\n ******* jwt_service._create_token tenant_id {tenant_id} \n\n")
        payload = {
            "sub": str(user_id),
            "type": token_type.value,
            "role": role,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "iat": datetime.utcnow(),
        }

        expire = datetime.utcnow() + (
            self.access_expires if token_type == TokenType.ACCESS else self.refresh_expires
        )
        payload.update({"exp": expire})

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_token_pair(
            self,
            user_id: int,
            role: str | None = None,
            tenant_id: str | None = None,
    ) -> dict[str, str]:
        """Create access + refresh token pair"""
        access = self._create_token(user_id, TokenType.ACCESS, role, tenant_id)
        refresh = self._create_token(user_id, TokenType.REFRESH, role, tenant_id)

        log.info(f"\n\n ******* jwt_service.create_token_pair tenant_id {tenant_id} \n\n")
        log.info(f"\n\n ******* jwt_service.create_token_pair refresh {refresh} \n\n")
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
        }

    def verify_token(self, token: str, token_type: TokenType) -> TokenPayload:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if payload.get("type") != token_type.value:
                raise HTTPException(status_code=401, detail="Invalid token type")
            return TokenPayload(**payload)
        except jwt.PyJWTError as e:
            raise HTTPException(status_code=401, detail="Invalid token") from e
