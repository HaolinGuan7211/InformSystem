from __future__ import annotations

import pytest

from backend.app.services.user_profile.models import UserProfile


@pytest.mark.asyncio
async def test_upsert_and_build_snapshot_matches_golden_flow(
    user_profile_service,
    load_user_profile_mock,
    load_golden,
) -> None:
    payload = load_user_profile_mock(
        "upstream_inputs",
        "graduation_material_submission__input__manual_profile_request.json",
    )
    await user_profile_service.upsert_profile(UserProfile.model_validate(payload))

    snapshot = await user_profile_service.build_snapshot("stu_001")
    expected = UserProfile.model_validate(load_golden("02_user_profile.json"))

    assert snapshot is not None
    assert snapshot.model_dump() == expected.model_dump()


@pytest.mark.asyncio
async def test_list_active_users_returns_complete_snapshots(
    user_profile_service,
    load_user_profile_mock,
) -> None:
    graduation_user = UserProfile.model_validate(
        load_user_profile_mock(
            "upstream_inputs",
            "graduation_material_submission__input__manual_profile_request.json",
        )
    )
    course_user = UserProfile.model_validate(
        load_user_profile_mock(
            "upstream_inputs",
            "course_schedule_change__input__manual_profile_request.json",
        )
    )

    await user_profile_service.upsert_profile(graduation_user)
    await user_profile_service.upsert_profile(course_user)

    snapshots = await user_profile_service.list_active_users(limit=10)
    snapshots_by_id = {snapshot.user_id: snapshot for snapshot in snapshots}

    assert set(snapshots_by_id) == {"stu_001", "stu_002"}
    assert snapshots_by_id["stu_001"].notification_preference.channels == ["app_push"]
    assert [course.course_id for course in snapshots_by_id["stu_002"].enrolled_courses] == [
        "CS210",
        "CS305",
    ]
