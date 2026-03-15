from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.services.campus_auth.models import CampusAuthRequest, CampusSessionHandle


class CampusAuthProvider(ABC):
    @abstractmethod
    async def authenticate(self, request: CampusAuthRequest) -> CampusSessionHandle:
        raise NotImplementedError
