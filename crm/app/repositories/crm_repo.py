"""CRM repositories."""
import uuid
from sqlalchemy import select
from repo.base import BaseRepository
from models.crm import CrmAccount, CrmLineConnection, CrmDialogLink


class CrmConnectionRepository(BaseRepository[CrmAccount]):
    def __init__(self, session):
        super().__init__(CrmAccount, session)

    async def get_by_tenant(
        self, tenant_id: uuid.UUID, crm_type: str = "bitrix24"
    ) -> CrmAccount | None:
        rows = await self.get_multi(
            filters={"tenant_id": tenant_id, "crm_type": crm_type, "is_active": True},
            limit=1,
        )
        return rows[0] if rows else None

    async def get_by_member_and_connector(self, member_id: str, connector_id: str) -> CrmLineConnection | None:
        stmt = (
            select(CrmLineConnection)
            .join(CrmAccount, CrmLineConnection.crm_account_id == CrmAccount.id)
            .where(
                CrmAccount.member_id == member_id,
                CrmLineConnection.connector_id == connector_id,
                CrmAccount.is_active.is_(True),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_member_id(self, member_id: str) -> CrmAccount | None:
        rows = await self.get_multi(
            filters={"member_id": member_id, "is_active": True},
            limit=1,
        )
        return rows[0] if rows else None

    async def get_by_line_and_connector(self, line_id: uuid.UUID, connector_id: str) -> CrmAccount | None:
        stmt = (
            select(CrmAccount)
            .join(CrmLineConnection, CrmLineConnection.crm_account_id == CrmAccount.id)
            .where(
                CrmLineConnection.line_id == line_id,
                CrmLineConnection.connector_id == connector_id,
                CrmLineConnection.is_active.is_(True),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_tenant_and_channel(self, tenant_id: uuid.UUID, channel_type: str) -> CrmAccount | None:
        stmt = (
            select(CrmAccount, CrmLineConnection)
            .join(CrmLineConnection, CrmLineConnection.crm_account_id == CrmAccount.id)
            .where(
                CrmAccount.tenant_id == tenant_id,
                CrmLineConnection.channel_type == channel_type,
                CrmAccount.is_active.is_(True),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None
        account, line_conn = row
        account.connector_id = line_conn.connector_id
        account.crm_line_id = line_conn.crm_line_id
        account.channel_type = line_conn.channel_type
        return account

    async def upsert_amo(
        self,
        tenant_id: uuid.UUID,
        domain: str,
        account_id: str,
        amojo_id: str,
        access_token_enc: str,
        refresh_token_enc: str,
    ) -> CrmAccount:
        rows = await self.get_multi(
            filters={"domain": domain, "crm_type": "amocrm"},
            limit=1,
        )
        if rows:
            update_data = {
                "tenant_id": tenant_id,
                "account_id": account_id,
                "access_token_enc": access_token_enc,
                "refresh_token_enc": refresh_token_enc,
                "is_active": True,
            }
            if amojo_id:
                update_data["amojo_id"] = amojo_id
            return await self.update(rows[0], **update_data)
        return await self.create(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            domain=domain,
            crm_type="amocrm",
            account_id=account_id,
            amojo_id=amojo_id,
            access_token_enc=access_token_enc,
            refresh_token_enc=refresh_token_enc,
            is_active=True,
        )

    async def get_by_amojo_id(self, amojo_id: str) -> CrmAccount | None:
        rows = await self.get_multi(
            filters={"amojo_id": amojo_id, "is_active": True},
            limit=1,
        )
        return rows[0] if rows else None





class CrmDialogLinkRepository(BaseRepository[CrmDialogLink]):
    def __init__(self, session):
        super().__init__(CrmDialogLink, session)

    async def get_by_conversation(
        self,
        conversation_id: uuid.UUID,
    ) -> CrmDialogLink | None:
        rows = await self.get_multi(
            filters={"conversation_id": conversation_id},
            limit=1,
        )
        return rows[0] if rows else None

    async def get_by_crm_chat_id(
        self,
        crm_chat_id: str,
    ) -> CrmDialogLink | None:
        rows = await self.get_multi(
            filters={"crm_chat_id": crm_chat_id},
            limit=1,
        )
        return rows[0] if rows else None