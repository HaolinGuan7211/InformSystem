from __future__ import annotations

from typing import Any

from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository


class CreditStatusManager:
    def __init__(self, repository: SQLiteUserProfileRepository) -> None:
        self._repository = repository

    async def get_credit_status(self, user_id: str) -> dict[str, Any]:
        profile = await self._repository.get_base_profile(user_id)
        return profile.credit_status if profile else {}
