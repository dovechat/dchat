from sqlalchemy.ext.asyncio import AsyncSession
from repo.base import BaseRepository
from models.crm import CrmSettings
import uuid

class CrmSettingsRepository(BaseRepository[CrmSettings]):
    def __init__(self, session: AsyncSession):
        super().__init__(CrmSettings, session)

    async def get_by_tenant(self, tenant_id: uuid.UUID) -> CrmSettings | None:
        rows = await self.get_multi(filters={"tenant_id": tenant_id}, limit=1)
        return rows[0] if rows else None