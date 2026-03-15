from __future__ import annotations

import pytest

from backend.app.shared.models import DecisionResult, DeliveryLog, OptimizationSample


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
        ),
        persist_delivery_fact=True,
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
    stored_log = await container.delivery_log_repository.get_by_log_id("dlv_failed_001")

    assert [sample.model_dump() for sample in exported] == [expected.model_dump()]
    assert stored_log is not None
    assert stored_log.status == "failed"


@pytest.mark.asyncio
async def test_delivery_outcome_sample_keeps_boundary_when_feedback_already_exists(
    container,
    feedback_service,
    load_feedback_mock,
    load_golden,
    seed_pipeline_records,
) -> None:
    await seed_pipeline_records(container)
    await container.delivery_log_repository.save(DeliveryLog.model_validate(load_golden("06_delivery_log.json")))
    await feedback_service.record_user_feedback(
        load_feedback_mock("upstream_inputs/graduation_material_submission__input__user_feedback.json")
    )

    await feedback_service.record_delivery_outcome(
        DeliveryLog.model_validate(
            load_feedback_mock(
                "upstream_inputs/graduation_material_submission__input__delivery_log_failed.json"
            )
        ),
        persist_delivery_fact=True,
    )
    exported = await feedback_service.export_optimization_samples(
        source="delivery_outcome",
        outcome_label="delivery_failed",
    )

    assert len(exported) == 1
    assert exported[0].source == "delivery_outcome"
    assert exported[0].outcome_label == "delivery_failed"
    assert exported[0].delivery_log_id == "dlv_failed_001"
    assert exported[0].metadata["delivery_status"] == "failed"


@pytest.mark.asyncio
async def test_sample_assembler_backfills_latest_decision_from_append_only_history(
    container,
    sample_assembler,
    load_feedback_mock,
    load_golden,
    seed_pipeline_records,
) -> None:
    await seed_pipeline_records(container)
    await container.delivery_log_repository.save(DeliveryLog.model_validate(load_golden("06_delivery_log.json")))

    latest_decision = DecisionResult.model_validate(load_golden("05_decision_result.json")).model_copy(
        update={
            "decision_id": "dec_latest_history",
            "priority_score": 88.0,
            "priority_level": "high",
            "generated_at": "2026-03-13T10:24:00+08:00",
        }
    )
    await container.decision_repository.save(latest_decision)

    feedback_record = await container.feedback_service.record_user_feedback(
        load_feedback_mock("upstream_inputs/graduation_material_submission__input__user_feedback.json")
    )
    sample = await sample_assembler.build_sample(
        feedback_record.event_id,
        feedback_record.user_id,
        feedback_record=feedback_record,
    )

    assert sample is not None
    assert sample.decision_id == "dec_latest_history"


@pytest.mark.asyncio
async def test_sample_assembler_backfills_latest_delivery_fact_from_canonical_history(
    container,
    sample_assembler,
    load_feedback_mock,
    load_golden,
    seed_pipeline_records,
) -> None:
    await seed_pipeline_records(container)
    await container.delivery_log_repository.save(DeliveryLog.model_validate(load_golden("06_delivery_log.json")))
    await container.delivery_log_repository.save(
        DeliveryLog.model_validate(
            load_feedback_mock(
                "upstream_inputs/graduation_material_submission__input__delivery_log_failed.json"
            )
        )
    )

    sample = await sample_assembler.build_sample("evt_001", "stu_001")

    assert sample is not None
    assert sample.source == "delivery_outcome"
    assert sample.outcome_label == "delivery_failed"
    assert sample.delivery_log_id == "dlv_failed_001"
    assert sample.metadata["delivery_status"] == "failed"
