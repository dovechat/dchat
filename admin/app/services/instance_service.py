"""Admin service: Green API instance pool management."""
import logging
from uuid import UUID

from fastapi import HTTPException, status

from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    BulkCleanRequest,
    CreateInstanceRequest,
    InstanceListResponse,
    InstanceOut,
    MessageResponse,
)
from models.lines import InstanceStatus
from services.cleanup_service import CleanupService
from repo.conversation_repo import ConversationRepository
from repo.line_repo import ChannelAccountRepository
from repo.message_repo import MessageRepository
from repo.instance_repo import InstanceRepository as MonoInstanceRepository

log = logging.getLogger("uvicorn.error")


class AdminInstanceService:

    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    async def list_instances(
        self,
        skip: int,
        limit: int,
        provider: str | None,
        status: str | None,
        actor_id: UUID,
    ) -> InstanceListResponse:
        instances = await self._uow.instances.get_all(
            skip=skip, limit=limit, provider=provider, status=status
        )
        total = len(instances)  # для небольших пулов достаточно
        idle_count = await self._uow.instances.count_by_status("idle")
        allocated_count = await self._uow.instances.count_by_status("allocated")

        '''
        await self._uow.audit.log(
            actor_id=actor_id,
            action="list_instances",
            resource_type="instance",
        )
        await self._uow.commit()
        '''

        return InstanceListResponse(
            items=[InstanceOut.model_validate(i) for i in instances],
            total=total,
            idle_count=idle_count,
            allocated_count=allocated_count,
        )

    async def get_instance(self, instance_id: UUID, actor_id: UUID) -> InstanceOut:
        instance = await self._uow.instances.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")

        '''
        await self._uow.audit.log(
            actor_id=actor_id,
            action="get_instance",
            resource_type="instance",
            resource_id=instance_id,
        )
        await self._uow.commit()
        return InstanceOut.model_validate(instance)
        '''

    async def create_instance(
        self,
        request: CreateInstanceRequest,
        actor_id: UUID,
    ) -> InstanceOut:
        # Проверяем уникальность external_id
        existing = await self._uow.instances.get_multi(
            filters={"external_id": request.external_id, "provider": request.provider}
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Instance with this external_id already exists",
            )

        instance = await self._uow.instances.create_instance(
            provider=request.provider,
            external_id=request.external_id,
        )

        await self._uow.audit.log(
            actor_id=actor_id,
            action="create_instance",
            resource_type="instance",
            resource_id=instance.id,
            details={"provider": request.provider, "external_id": request.external_id},
        )
        await self._uow.commit()

        log.info(f"Admin {actor_id}: created instance {instance.id} ({request.provider}/{request.external_id})")
        return InstanceOut.model_validate(instance)

    async def clean_instance(self, instance_id: UUID, actor_id: UUID) -> MessageResponse:
        """
        Принудительная очистка инстанса:
        1. Снимаем привязку к линии
        2. Переводим в idle
        3. Логируем событие

        Реальный разлогин у провайдера — задача для воркера/коннектора,
        здесь фиксируем намерение и меняем статус.
        """
        instance = await self._uow.instances.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")

        old_line_id = instance.allocated_to_line_id

        if old_line_id:
            channel_account_repo = ChannelAccountRepository(self._uow._session)
            channels = await channel_account_repo.get_by_line(old_line_id)
            cleanup = CleanupService(
                conversation_repo=ConversationRepository(self._uow._session),
                message_repo=MessageRepository(self._uow._session),
                channel_account_repo=channel_account_repo,
                instance_repo=MonoInstanceRepository(self._uow._session),
            )
            for ch in channels:
                await cleanup.cleanup_line(old_line_id, channel_type=ch.channel_type.value)
            if not any(ch.channel_type.value == "whatsapp_green" for ch in channels):
                await self._uow.instances.release(instance)
        else:
            await self._uow.instances.release(instance)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="clean_instance",
            resource_type="instance",
            resource_id=instance_id,
            details={"was_allocated_to": str(old_line_id) if old_line_id else None},
        )
        await self._uow.commit()

        log.info(f"Admin {actor_id}: cleaned instance {instance_id} (was on line {old_line_id})")
        return MessageResponse(message="Instance cleaned and returned to pool")

    async def bulk_clean(self, request: BulkCleanRequest, actor_id: UUID) -> MessageResponse:
        """Массовая очистка группы инстансов."""
        cleaned = 0
        errors = []

        for instance_id in request.instance_ids:
            instance = await self._uow.instances.get_instance(instance_id)
            if not instance:
                errors.append(str(instance_id))
                continue

            old_line_id = instance.allocated_to_line_id
            await self._uow.instances.release(instance)

            await self._uow.audit.log(
                actor_id=actor_id,
                action="bulk_clean_instance",
                resource_type="instance",
                resource_id=instance_id,
                details={"was_allocated_to": str(old_line_id) if old_line_id else None},
            )
            cleaned += 1

        await self._uow.commit()

        log.info(f"Admin {actor_id}: bulk clean — {cleaned} instances cleaned, {len(errors)} not found")
        msg = f"Cleaned {cleaned} instances"
        if errors:
            msg += f". Not found: {', '.join(errors)}"
        return MessageResponse(message=msg)

    async def delete_instance(self, instance_id: UUID, actor_id: UUID) -> MessageResponse:
        instance = await self._uow.instances.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")

        if instance.status == InstanceStatus.busy:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete allocated instance. Clean it first.",
            )

        await self._uow.audit.log(
            actor_id=actor_id,
            action="delete_instance",
            resource_type="instance",
            resource_id=instance_id,
            details={"external_id": instance.external_id, "provider": instance.provider},
        )
        await self._uow.instances.delete(instance)
        await self._uow.commit()

        log.info(f"Admin {actor_id}: deleted instance {instance_id}")
        return MessageResponse(message="Instance deleted")


    async def reallocate_instance(self, instance_id: UUID, line_id: UUID, actor_id: UUID) -> MessageResponse:
        instance = await self._uow.instances.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    
        old_line_id = instance.allocated_to_line_id
        await self._uow.instances.allocate(instance, line_id)
    
        await self._uow.audit.log(
            actor_id=actor_id,
            action="reallocate_instance",
            resource_type="instance",
            resource_id=instance_id,
            details={
                "old_line_id": str(old_line_id) if old_line_id else None,
                "new_line_id": str(line_id),
            },
        )
        await self._uow.commit()
    
        log.info(f"Admin {actor_id}: reallocated instance {instance_id} from line {old_line_id} to {line_id}")
        return MessageResponse(message="Instance reallocated")