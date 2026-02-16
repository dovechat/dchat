import json
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.lines import Line, Instance, ChannelAccount, InstanceStatus
from repo.base import BaseRepository
import logging

log = logging.getLogger("uvicorn.error")


class LineRepository(BaseRepository[Line]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Line, session)

    async def create_line(
            self,
            tenant_id: uuid.UUID,
            name: str,
            channel_type: str,
            expires_at: Optional[datetime] = None,
            is_demo: bool = False,
    ) -> Line:
        return await self.create(
            tenant_id=tenant_id,
            name=name,
            channel_type=channel_type,
            expires_at=expires_at,
            is_demo=is_demo,
            connection_state={"status": "not_connected"}
        )

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

    async def update_line(
            self,
            line: Line,
            **data
    ) -> Line:
        return await self.update(line, **data)

    async def delete_line(
            self,
            line: Line
    ) -> None:
        await self.delete(line)


class InstanceRepository(BaseRepository[Instance]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Instance, session)

    async def get_free_instance(self, provider: str = "green_api") -> Instance | None:
        query = select(Instance).where(
            Instance.provider == provider,
            Instance.status == InstanceStatus.idle,
            Instance.allocated_to_line_id.is_(None)
        ).limit(1)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_instance(
            self,
            provider: str,
            external_id: str
    ) -> Instance:
        return await self.create(
            provider=provider,
            external_id=external_id,
            status=InstanceStatus.idle
        )

    async def allocate_instance(
            self,
            instance: Instance,
            line_id: uuid.UUID
    ) -> Instance:
        return await self.update(
            instance,
            status=InstanceStatus.busy,
            allocated_to_line_id=line_id
        )

    async def release_instance(
            self,
            instance: Instance
    ) -> Instance:
        return await self.update(
            instance,
            status=InstanceStatus.idle,
            allocated_to_line_id=None,
            last_cleanup_at=datetime.utcnow()
        )

    async def get_instance_by_line(
            self,
            line_id: uuid.UUID
    ) -> Instance | None:
        query = select(Instance).where(
            Instance.allocated_to_line_id == line_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class ChannelAccountRepository(BaseRepository[ChannelAccount]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ChannelAccount, session)

    async def create_account(
            self,
            line_id: uuid.UUID,
            credentials_encrypted: dict,
            state_json: Optional[dict] = None
    ) -> ChannelAccount:

        data_dict = {}
        data_dict["credentials_encrypted"] = data["credentials_encrypted"]
        enc_data = json.loads(data["credentials_encrypted"]["encrypted_data"])

        return await self.create(
            line_id=line_id,
            credentials_encrypted=credentials_encrypted,
            state_json=state_json or {},
            phone=enc_data["phone"],
            session_string=enc_data["session_string"],
        )

    async def get_by_line(
            self,
            line_id: uuid.UUID
    ) -> ChannelAccount | None:
        existing = await self.get_multi(
            filters={"line_id": line_id},
            limit=1
        )
        return existing[0] if existing else None

   
    async def update_account(
            self,
            account: ChannelAccount,
            **data
    ) -> ChannelAccount:
        import copy
        log.info(f"--------------- ChannelAccountRepository.update_account account {account} data {type(data)} {data['credentials_encrypted']}")

        data_dict = {}
        data_dict["credentials_encrypted"] = data["credentials_encrypted"]
        enc_data = json.loads(data["credentials_encrypted"]["encrypted_data"])
        log.info(enc_data["phone"])
    
        log.info(enc_data["session_string"])
        data_dict["phone"] = enc_data["phone"]
        data_dict["session_string"] = enc_data["session_string"]
        log.info(f"--------------- phone {data_dict['phone']} ")
        log.info(f"--------------- session_string {data_dict['session_string']} ")
        log.info(f"--------------- data_dict {type(data_dict)} {data_dict}")
        return await self.update(account, **data_dict)