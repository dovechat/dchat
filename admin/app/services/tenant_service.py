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
    TenantOut,
    TenantListResponse,
    SetTenantStatusRequest,
    MessageResponse,
    UpdateTenantRequest,
)

log = logging.getLogger("uvicorn.error")


class AdminTenantService:

    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    # ── Users ──────────────────────────────────────────────────────────────

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

        return UserListResponse(
            items=[UserOut.model_validate(u) for u in users],
            total=total,
        )

    async def get_user(self, user_id: UUID, actor_id: UUID) -> UserOut:
        user = await self._uow.users.get_user(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

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

    # ── Tenants ────────────────────────────────────────────────────────────

    async def list_tenants(
        self,
        skip: int,
        limit: int,
        name: str | None,
        status: str | None,
        payment: str | None,
        locale: str | None,
        actor_id: UUID,
    ) -> TenantListResponse:
        filters = {}
        if name:
            filters["name"] = f"%{name}%"
        if status:
            filters["status"] = status
        if payment:
            filters["payment"] = payment
        if locale:
            filters["locale"] = locale

        tenants = await self._uow.tenants.get_multi(
            skip=skip, limit=limit,
            filters=filters or None,
            order_by=[("name", "asc")],
        )
        total = await self._uow.tenants.count(filters=filters or None)

        return TenantListResponse(
            items=[TenantOut.model_validate(t) for t in tenants],
            total=total,
        )

    async def get_tenant(self, tenant_id: UUID, actor_id: UUID) -> TenantOut:
        tenant = await self._uow.tenants.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Компания не найдена")

        return TenantOut.model_validate(tenant)

    async def set_tenant_status(
        self,
        tenant_id: UUID,
        request: SetTenantStatusRequest,
        actor_id: UUID,
    ) -> MessageResponse:
        tenant = await self._uow.tenants.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Компания не найдена")

        old_status = tenant.status
        await self._uow.tenants.update(tenant, status=request.status.value)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="set_tenant_status",
            resource_type="tenant",
            resource_id=tenant_id,
            details={
                "old_status": old_status.value if hasattr(old_status, "value") else old_status,
                "new_status": request.status.value,
            },
        )
        await self._uow.commit()

        log.info(f"Admin {actor_id}: tenant {tenant_id} status {old_status} → {request.status.value}")
        return MessageResponse(message=f"Статус компании изменён на {request.status.value}")

    
    async def update_tenant(self, tenant_id: UUID, request: UpdateTenantRequest, actor_id: UUID) -> TenantOut:
        tenant = await self._uow.tenants.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Компания не найдена")
    
        data = request.model_dump(exclude_none=True)
        await self._uow.tenants.update(tenant, **data)
        await self._uow.audit.log(
            actor_id=actor_id,
            action="update_tenant",
            resource_type="tenant",
            resource_id=tenant_id,
            details=data,
        )
        await self._uow.commit()
        return TenantOut.model_validate(tenant)