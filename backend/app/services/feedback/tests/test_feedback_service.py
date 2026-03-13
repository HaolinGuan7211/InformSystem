from __future__ import annotations

import pytest

from backend.app.shared.models import UserFeedbackRecord


@pytest.mark.asyncio
async def test_feedback_service_is_idempotent_for_same_feedback_id(
    container,
    feedback_service,
    load_feedback_mock,
    seed_pipeline_records,
) -> None:
    await seed_pipeline_records(container)
    payload = load_feedback_mock("upstream_inputs/graduation_material_submission__input__user_feedback.json")

    first = await feedback_service.record_user_feedback(payload)
    second = await feedback_service.record_user_feedback({**payload, "comment": "重复提交"})
    records = await container.feedback_repository.list_by_user("stu_001")

    assert isinstance(first, UserFeedbackRecord)
    assert second.model_dump() == first.model_dump()
    assert len(records) == 1
