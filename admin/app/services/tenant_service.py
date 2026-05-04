"""Admin service: users and tenants management."""
import logging
from uuid import UUID

from fastapi import HTTPException, status

from core.security import get_password_hash
from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    UserOut,
    UserListResponse,
    SetUserStatusRequest,
    ResetPasswordRequest,
    MessageResponse,
)

log = logging.getLogger("uvicorn.error")


class AdminTenantService:

    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    async def list_users(
        self,
        skip: int,
        limit: int,
        role: str | None,
        status: str | None,
        email: str | None,
        actor_id: UUID,
    ) -> UserListResponse:
        users = await self._uow.users.get_all_users(
            skip=skip, limit=limit, role=role, status=status, email=email
        )
        total = await self._uow.users.count_users(role=role, status=status)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="list_users",
            resource_type="user",
            details={"filters": {"role": role, "status": status, "email": email}},
        )
        await self._uow.commit()

        return UserListResponse(
            items=[UserOut.model_validate(u) for u in users],
            total=total,
        )

    async def get_user(self, user_id: UUID, actor_id: UUID) -> UserOut:
        user = await self._uow.users.get_user(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        await self._uow.audit.log(
            actor_id=actor_id,
            action="get_user",
            resource_type="user",
            resource_id=user_id,
        )
        await self._uow.commit()
        return UserOut.model_validate(user)

    async def set_user_status(
        self,
        user_id: UUID,
        request: SetUserStatusRequest,
        actor_id: UUID,
    ) -> MessageResponse:
        user = await self._uow.users.get_user(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        old_status = user.status
        await self._uow.users.set_user_status(user, request.status.value)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="set_user_status",
            resource_type="user",
            resource_id=user_id,
            details={"old_status": old_status.value if hasattr(old_status, 'value') else old_status, "new_status": request.status.value},
        )
        await self._uow.commit()

        log.info(f"Admin {actor_id}: user {user_id} status changed {old_status} → {request.status.value}")
        return MessageResponse(message=f"User status updated to {request.status.value}")

    async def reset_password(
        self,
        user_id: UUID,
        request: ResetPasswordRequest,
        actor_id: UUID,
    ) -> MessageResponse:
        user = await self._uow.users.get_user(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        new_hash = get_password_hash(request.new_password)
        await self._uow.users.set_user_password_hash(user, new_hash)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="reset_password",
            resource_type="user",
            resource_id=user_id,
        )
        await self._uow.commit()

        log.info(f"Admin {actor_id}: password reset for user {user_id}")
        return MessageResponse(message="Password reset successfully")