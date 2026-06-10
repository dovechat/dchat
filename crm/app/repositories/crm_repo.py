"""CRM repositories."""
import uuid
from repo.base import BaseRepository
from models.crm import CrmConnection, CrmDialogLink


class CrmConnectionRepository(BaseRepository[CrmConnection]):
    def __init__(self, session):
        super().__init__(CrmConnection, session)

    async def get_by_tenant(
        self, tenant_id: uuid.UUID, crm_type: str = "bitrix24"
    ) -> CrmConnection | None:
        rows = await self.get_multi(
            filters={"tenant_id": tenant_id, "crm_type": crm_type, "is_active": True},
            limit=1,
        )
        return rows[0] if rows else None

    async def get_by_member_and_connector(self, member_id: str, connector_id: str) -> CrmConnection | None:
        rows = await self.get_multi(
            filters={"member_id": member_id, "connector_id": connector_id, "is_active": True},
            limit=1,
        )
        return rows[0] if rows else None

    async def get_by_member_id(self, member_id: str) -> CrmConnection | None:
        rows = await self.get_multi(
            filters={"member_id": member_id, "is_active": True},
            limit=1,
        )
        return rows[0] if rows else None

    async def get_by_line_and_connector(self, line_id: uuid.UUID, connector_id: str) -> CrmConnection | None:
        rows = await self.get_multi(
            filters={"line_id": line_id, "connector_id": connector_id}, limit=1
        )
        return rows[0] if rows else None



class CrmDialogLinkRepository(BaseRepository[CrmDialogLink]):
    def __init__(self, session):
        super().__init__(CrmDialogLink, session)

    async def get_by_conversation(
        self,
        conversation_id: uuid.UUID,
        crm_connection_id: uuid.UUID,
    ) -> CrmDialogLink | None:
        rows = await self.get_multi(
            filters={
                "conversation_id": conversation_id,
                "crm_connection_id": crm_connection_id,
            },
            limit=1,
        )
        return rows[0] if rows else None


