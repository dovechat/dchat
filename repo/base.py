"""Base repository with common CRUD operations."""
import uuid
from typing import Any, Generic, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Base

import logging
log = logging.getLogger("uvicorn.error")

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    """Base repository for all models."""

    def __init__(self, model: type[ModelType], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, id: uuid.UUID, **filters: Any) -> ModelType | None:
        """Get record by UUID with optional filters."""
        query = select(self.model).where(self.model.id == id)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key) and value is not None:
                    query = query.where(getattr(self.model, key) == value)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_multi(
            self,
            *,
            skip: int = 0,
            limit: int = 100,
            filters: dict[str, Any] | None = None,
            join_model: Any | None = None,
            order_by: list[tuple[str, str]] | None = None,
    ) -> list[ModelType]:
        query = select(self.model)

        if join_model:
            query = query.join(join_model)

        if filters:
            for key, value in filters.items():
                target = None
                if hasattr(self.model, key):
                    target = self.model
                elif join_model and hasattr(join_model, key):
                    target = join_model

                if target and value is not None:
                    column = getattr(target, key)
                    if isinstance(value, list):
                        query = query.where(column.in_(value))
                    else:
                        query = query.where(column == value)

        if order_by:
            query = query.order_by(*[
                getattr(self.model, f).desc() if d == 'desc' else getattr(self.model, f).asc()
                for f, d in order_by
            ])

        result = await self.session.execute(query.offset(skip).limit(limit))
        items = list(result.scalars().all())
        return items

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count records."""
        query = select(func.count()).select_from(self.model)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key) and value is not None:
                    query = query.where(getattr(self.model, key) == value)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def create(self, **data: Any) -> ModelType:
        """Create new record."""
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: ModelType, **data: Any) -> ModelType:
        """Update existing record."""
        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)

        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelType) -> None:
        """Delete record."""
        await self.session.delete(instance)
        await self.session.flush()

    async def exists(self, **filters: Any) -> bool:
        """Check if record exists."""
        query = select(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)

        result = await self.session.execute(query.limit(1))
        return result.scalar_one_or_none() is not None
