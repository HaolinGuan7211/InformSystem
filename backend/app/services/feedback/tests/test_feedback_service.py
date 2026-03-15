from __future__ import annotations

import pytest

from backend.app.shared.models import DeliveryLog, UserFeedbackRecord


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


@pytest.mark.asyncio
async def test_feedback_service_workflow_callback_does_not_duplicate_canonical_delivery_log(
    container,
    feedback_service,
    load_golden,
    seed_pipeline_records,
) -> None:
    await seed_pipeline_records(container)
    existing = DeliveryLog.model_validate(load_golden("06_delivery_log.json"))
    await container.delivery_log_repository.save(existing)

    await feedback_service.record_delivery_outcome(existing)

    stored = await container.delivery_log_repository.get_by_log_id(existing.log_id)
    history = await container.delivery_log_repository.list_by_task(existing.task_id)

    assert stored is not None
    assert stored.model_dump() == existing.model_dump()
    assert [log.log_id for log in history] == [existing.log_id]
