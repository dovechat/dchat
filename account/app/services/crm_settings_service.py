import uuid
from infra.crypto import decrypt, encrypt
from repo.crm_repo import CrmAccountRepository, CrmSettingsRepository
from models.crm import CrmAccount, CrmSettings


class CrmSettingsService:
    def __init__(self, settings_repo: CrmSettingsRepository, account_repo: CrmAccountRepository):
        self.settings_repo = settings_repo
        self.account_repo = account_repo

    async def get(self, tenant_id: uuid.UUID) -> dict:
        settings = await self.settings_repo.get_by_tenant(tenant_id)
        account = await self.account_repo.get_by_tenant(tenant_id)
        result = settings.__dict__.copy() if settings else {}
        result["bitrix_client_id_set"] = bool(account and account.bitrix_client_id_enc)
        result["bitrix_client_secret_set"] = bool(account and account.bitrix_client_secret_enc)
        return result

    async def upsert(self, tenant_id: uuid.UUID, **data) -> CrmSettings:
        secrets = {k: data.pop(k) for k in list(data) if k in ("bitrix_client_id", "bitrix_client_secret")}
        if secrets:
            await self.upsert_account(tenant_id, **secrets)
        existing = await self.settings_repo.get_by_tenant(tenant_id)
        if existing:
            return await self.settings_repo.update(existing, **data)
        return await self.settings_repo.create(tenant_id=tenant_id, **data)

    async def upsert_account(self, tenant_id: uuid.UUID, **secrets):
        account = await self.account_repo.get_by_tenant(tenant_id)
        if not account:
            return
        updating = {}
        if "bitrix_client_id" in secrets:
            updating["bitrix_client_id_enc"] = encrypt(secrets["bitrix_client_id"])
        if "bitrix_client_secret" in secrets:
            updating["bitrix_client_secret_enc"] = encrypt(secrets["bitrix_client_secret"])
        await self.account_repo.update(account, **updating)