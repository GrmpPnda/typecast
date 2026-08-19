from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import BaseModel
from app.repositories.base import BaseRepository

T = TypeVar("T", bound=BaseModel)


class SQLAlchemyRepository(BaseRepository[T], Generic[T]):
    def __init__(self, session: AsyncSession, model_class: type[T]):
        self.session = session
        self.model_class = model_class

    async def get_by_id(self, id: uuid.UUID) -> T | None:
        return await self.session.get(self.model_class, id)

    async def get_all(self, **filters) -> list[T]:
        stmt = select(self.model_class)
        for key, value in filters.items():
            if value is not None and hasattr(self.model_class, key):
                stmt = stmt.where(getattr(self.model_class, key) == value)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> T:
        instance = self.model_class(**kwargs)
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: uuid.UUID, **kwargs) -> T | None:
        instance = await self.get_by_id(id)
        if instance is None:
            return None
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def delete(self, id: uuid.UUID) -> bool:
        instance = await self.get_by_id(id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.commit()
        return True
