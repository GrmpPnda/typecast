from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    @abstractmethod
    async def get_by_id(self, id: uuid.UUID) -> T | None: ...

    @abstractmethod
    async def get_all(self, **filters) -> list[T]: ...

    @abstractmethod
    async def create(self, **kwargs) -> T: ...

    @abstractmethod
    async def update(self, id: uuid.UUID, **kwargs) -> T | None: ...

    @abstractmethod
    async def delete(self, id: uuid.UUID) -> bool: ...
