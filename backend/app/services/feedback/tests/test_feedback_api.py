from __future__ import annotations

import asyncio


def test_feedback_api_records_feedback_and_exports_samples(
    client,
    load_feedback_mock,
    load_golden,
    seed_pipeline_records,
) -> None:
    container = client.app.state.container
    asyncio.run(seed_pipeline_records(container))

    delivery_response = client.post(
        "/api/v1/feedback/delivery-outcomes",
        json=load_golden("06_delivery_log.json"),
    )
    assert delivery_response.status_code == 200
    assert delivery_response.json() == {"success": True, "log_id": "dlv_001"}

    feedback_response = client.post(
        "/api/v1/feedback",
        json=load_feedback_mock(
            "upstream_inputs/graduation_material_submission__input__user_feedback.json"
        ),
    )
    assert feedback_response.status_code == 200
    assert feedback_response.json() == {"success": True, "feedback_id": "fb_002"}

    stored_log = asyncio.run(container.delivery_log_repository.get_by_log_id("dlv_001"))
    assert stored_log is not None
    assert stored_log.status == "sent"

    export_response = client.get(
        "/api/v1/feedback/optimization-samples",
        params={"source": "user_feedback"},
    )
    assert export_response.status_code == 200
    assert export_response.json() == {
        "success": True,
        "count": 1,
        "items": [
            load_feedback_mock(
                "downstream_outputs/graduation_material_submission__output__optimization_sample_false_positive.json"
            )
        ],
    }
