import uuid
from repo.base import BaseRepository
from models.crm import CrmLineConnection


class CrmLineConnectionRepository(BaseRepository[CrmLineConnection]):
    def __init__(self, session):
        super().__init__(CrmLineConnection, session)

    async def get_by_account(self, crm_account_id: uuid.UUID) -> list[CrmLineConnection]:
        return await self.get_multi(
            filters={"crm_account_id": crm_account_id, "is_active": True},
        )

    async def get_by_line(self, line_id: uuid.UUID) -> CrmLineConnection | None:
        rows = await self.get_multi(
            filters={"line_id": line_id, "is_active": True},
            limit=1,
        )
        return rows[0] if rows else None

    async def get_by_line_and_channel(
        self, line_id: uuid.UUID, channel_type: str
    ) -> CrmLineConnection | None:
        rows = await self.get_multi(
            filters={"line_id": line_id, "channel_type": channel_type, "is_active": True},
            limit=1,
        )
        return rows[0] if rows else None

class CrmAccountRepository(BaseRepository[CrmAccount]):
    def __init__(self, session):
        super().__init__(CrmAccount, session)
