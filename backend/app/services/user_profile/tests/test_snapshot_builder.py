from __future__ import annotations

import pytest

from backend.app.services.user_profile.models import NotificationPreference, UserProfile


@pytest.mark.asyncio
async def test_snapshot_builder_supports_progressive_completion_defaults(
    user_profile_repository,
    snapshot_builder,
) -> None:
    await user_profile_repository.save(
        UserProfile(
            user_id="stu_sparse",
            student_id="20269999",
            college="计算机学院",
        )
    )

    snapshot = await snapshot_builder.build("stu_sparse")

    assert snapshot is not None
    assert snapshot.enrolled_courses == []
    assert snapshot.credit_status == {}
    assert snapshot.current_tasks == []
    assert snapshot.notification_preference.model_dump() == NotificationPreference().model_dump()


@pytest.mark.asyncio
async def test_snapshot_builder_returns_none_for_unknown_user(snapshot_builder) -> None:
    assert await snapshot_builder.build("stu_missing") is None
