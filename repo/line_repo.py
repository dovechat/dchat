import json
import uuid
from datetime import datetime
from sqlalchemy import select, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from models.lines import ChannelAccount, Line, LineStatus
from models.tenants import Tenant
from repo.base import BaseRepository
from schemas.line_schemas import ChannelType
import logging

log = logging.getLogger("uvicorn.error")


class LineRepository(BaseRepository[Line]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Line, session)

    async def get_lines_by_tenant(
            self,
            tenant_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> list[Line]:
        return await self.get_multi(
            skip=skip,
            limit=limit,
            filters={"tenant_id": tenant_id}
        )

    async def get_line_by_id(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID
    ) -> Line | None:
        return await self.get_by_id(line_id, tenant_id=tenant_id)

    async def get_lines_to_expire(self, now: datetime) -> list[Line]:
        result = await self.session.execute(
            select(Line)
            .where(Line.expires_at <= now)
            .where(Line.status == LineStatus.active)
            .where(Line.expires_at.is_not(None))
        )
        return list(result.scalars().all())

    async def get_active_lines(self) -> list[Line]:
        return await self.get_multi(
            filters={"status": [LineStatus.active, LineStatus.expired]},
            limit=10000,
        )

    async def get_lines_with_channels_by_tenant(self, tenant_id: uuid.UUID):
        return await self.get_multi(0, 20, {"tenant_id": tenant_id}, ChannelAccount)

    async def update_connection_state(self, line_id: uuid.UUID, state: dict) -> None:
        line = await self.get_by_id(line_id)
        if line:
            await self.update(line, connection_state=state)

    async def set_line_status(self, line_id: str, state: dict):
        """Update status to active using base update logic"""
        line = await self.get_by_id(line_id)
        if line:
            res = await self.update(line, connection_state=state)
            return res


class ChannelAccountRepository(BaseRepository[ChannelAccount]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ChannelAccount, session)

    async def create_account(
            self,
            line_id: uuid.UUID,
            channel_type: ChannelType,
            credentials_encrypted: dict,
            expires_at: datetime | None = None,
            phone: str | None = None,
            session_string: str | None = None,
            bot_token: str | None = None,
            state_json: dict | None = None
    ) -> ChannelAccount:

        log.info(f"credentials_encrypted {type(credentials_encrypted)} {credentials_encrypted}")

        return await self.create(
            line_id=line_id,
            channel_type=channel_type,
            credentials_encrypted=credentials_encrypted,
            expires_at=expires_at,
            state_json=state_json or {},
            phone=phone,
            session_string=session_string,
            bot_token=bot_token,
        )

    async def get_by_line(
            self,
            line_id: uuid.UUID
    ) -> list[ChannelAccount]:
        return await self.get_multi(
            filters={"line_id": line_id},
        )

    async def get_by_line_and_type(
            self,
            line_id: uuid.UUID,
            channel_type: ChannelType
    ) -> ChannelAccount | None:
        existing = await self.get_multi(
            filters={"line_id": line_id, "channel_type": channel_type},
            limit=1
        )
        return existing[0] if existing else None

    async def update_account(
        self,
        account: ChannelAccount,
        **data,
    ) -> ChannelAccount:
        return await self.update(account, **data)

    async def update_connection_status(
            self,
            line_id: uuid.UUID,
            status: str,
            channel_type: ChannelType,
            connection_error: str | None = None,
            phone: str | None = None
    ) -> None:
        account = await self.get_by_line_and_type(line_id, channel_type)
        if account:
            await self.update(
                account,
                connection_status=status,
                last_checked_at=datetime.now(),
                connection_error=connection_error,
                phone=phone,
            )

    async def get_expired(self, now: datetime) -> list:
        from sqlalchemy import select
        result = await self.session.execute(
            select(ChannelAccount).where(
                ChannelAccount.expires_at.is_not(None),
                ChannelAccount.expires_at < now,
            )
        )
        return result.scalars().all()

    async def get_one_per_channel_type(self, channel_type: str | None = None):
        from sqlalchemy import select
        from models.messages import Conversation

        query = (
            select(self.model)
            .join(
                Conversation,
                (Conversation.line_id == self.model.line_id)
                & (Conversation.channel_type == self.model.channel_type),
            )
            .where(self.model.credentials_encrypted.isnot(None))
            .distinct(self.model.channel_type)
            .order_by(self.model.channel_type, Conversation.created_at.desc())
        )

        result = await self.session.execute(query)
        return result.scalars().all()


from models.lines import Instance

class InstanceRepository(BaseRepository[Instance]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Instance, session)

    async def get_by_line(self, line_id: uuid.UUID) -> Instance | None:
        query = select(Instance).where(Instance.allocated_to_line_id == line_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()