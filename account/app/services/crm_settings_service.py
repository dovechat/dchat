import uuid
from repo.crm_settings_repo import CrmSettingsRepository
from models.crm import CrmSettings


class CrmSettingsService:
    def __init__(self, repo: CrmSettingsRepository):
        self._repo = repo

    async def get(self, tenant_id: uuid.UUID) -> CrmSettings | None:
        return await self._repo.get_by_tenant(tenant_id)

    async def upsert(self, tenant_id: uuid.UUID, **data) -> CrmSettings:
        existing = await self._repo.get_by_tenant(tenant_id)
        if existing:
            return await self._repo.update(existing, **data)
        return await self._repo.create(tenant_id=tenant_id, **data)