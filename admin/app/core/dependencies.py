"""FastAPI dependencies for admin service."""
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from app.core.uow import AdminUnitOfWork
from app.repositories.billing_repo import (
    BalanceLedgerRepository,
    BalanceRepository,
    PaymentRepository,
    TariffRepository
)
from app.services.billing_service import AdminBillingService

bearer_scheme = HTTPBearer()


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.PyJWTError:
        return None


async def get_tariff_repo(db: AsyncSession = Depends(get_db)) -> TariffRepository:
    return TariffRepository(db)


async def get_uow(db: AsyncSession = Depends(get_db)) -> AdminUnitOfWork:
    return AdminUnitOfWork(db)


async def get_billing_service(
    uow: AdminUnitOfWork = Depends(get_uow),
) -> AdminBillingService:
    return AdminBillingService(uow)




async def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    payload = decode_token(credentials.credentials)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return payload


AdminUser = Annotated[dict, Depends(get_current_admin)]
DBSession = Annotated[AsyncSession, Depends(get_db)]