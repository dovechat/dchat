"""FastAPI dependencies for CRM service."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from app.core.uow import CrmUnitOfWork
from app.services.crm_service import CrmService


async def get_uow(session: AsyncSession = Depends(get_db)) -> CrmUnitOfWork:
    return CrmUnitOfWork(session)


async def get_crm_service(uow: CrmUnitOfWork = Depends(get_uow)) -> CrmService:
    return CrmService(uow)
