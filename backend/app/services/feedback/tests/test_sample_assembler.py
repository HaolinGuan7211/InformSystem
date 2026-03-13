from __future__ import annotations

import pytest

from backend.app.shared.models import DeliveryLog, OptimizationSample


@pytest.mark.asyncio
async def test_sample_assembler_builds_false_positive_sample(
    container,
    sample_assembler,
    load_feedback_mock,
    load_golden,
    seed_pipeline_records,
) -> None:
    await seed_pipeline_records(container)
    await container.delivery_log_repository.save(DeliveryLog.model_validate(load_golden("06_delivery_log.json")))

    feedback_record = await container.feedback_service.record_user_feedback(
        load_feedback_mock("upstream_inputs/graduation_material_submission__input__user_feedback.json")
    )

    sample = await sample_assembler.build_sample(
        feedback_record.event_id,
        feedback_record.user_id,
        feedback_record=feedback_record,
    )
    expected = OptimizationSample.model_validate(
        load_feedback_mock(
            "downstream_outputs/graduation_material_submission__output__optimization_sample_false_positive.json"
        )
    )

    assert sample is not None
    assert sample.model_dump() == expected.model_dump()


@pytest.mark.asyncio
async def test_feedback_service_exports_delivery_failed_sample(
    container,
    feedback_service,
    load_feedback_mock,
    seed_pipeline_records,
) -> None:
    await seed_pipeline_records(container)

    await feedback_service.record_delivery_outcome(
        DeliveryLog.model_validate(
            load_feedback_mock(
                "upstream_inputs/graduation_material_submission__input__delivery_log_failed.json"
            )
        )
    )
    exported = await feedback_service.export_optimization_samples(
        source="delivery_outcome",
        outcome_label="delivery_failed",
    )
    expected = OptimizationSample.model_validate(
        load_feedback_mock(
            "downstream_outputs/graduation_material_submission__output__optimization_sample_delivery_failed.json"
        )
    )

    assert [sample.model_dump() for sample in exported] == [expected.model_dump()]
