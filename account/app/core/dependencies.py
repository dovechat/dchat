from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from fastapi import Depends
from app.repositories.tenant_repo import RequisitsRepository, TenantRepository


async def get_tenant_repo(db: AsyncSession = Depends(get_db)) -> TenantRepository:
    """Get tenant repository instance."""
    return TenantRepository(db)

async def get_requisits_repo(db: AsyncSession = Depends(get_db)) -> RequisitsRepository:
    """Get tenant repository instance."""
    return RequisitsRepository(db)
