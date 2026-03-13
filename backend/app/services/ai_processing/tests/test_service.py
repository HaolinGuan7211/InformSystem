from __future__ import annotations

import pytest

from backend.app.services.ai_processing.model_gateway import MockModelGateway
from backend.app.services.ai_processing.models import AIAnalysisResult, AIModelConfig, GatewayResponse


class InvalidJSONGateway(MockModelGateway):
    async def invoke(self, prompt, model_config: AIModelConfig) -> GatewayResponse:
        self.invocation_count += 1
        return GatewayResponse(
            provider="mock",
            model_name=model_config.model_name,
            content="not-json",
            raw_request_ref="bad_req",
            raw_response_ref="bad_resp",
            latency_ms=3,
        )


@pytest.mark.asyncio
async def test_ai_processing_service_matches_golden_flow(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
    load_golden,
) -> None:
    fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    service, repository, gateway = build_ai_service(fixture_response=fixture)

    result = await service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["user_profile"],
    )
    expected = AIAnalysisResult.model_validate(load_golden("04_ai_analysis_result.json"))

    assert result.model_dump() == expected.model_dump()
    stored = await repository.get_by_event_and_user(
        "evt_001",
        "stu_001",
        model_name="gpt-5-mini",
        prompt_version="prompt_v1",
    )
    assert stored is not None
    assert stored.model_dump() == expected.model_dump()
    call_logs = await repository.list_call_logs("evt_001", "stu_001")
    assert len(call_logs) == 1
    assert call_logs[0].status == "success"
    assert gateway.invocation_count == 1


@pytest.mark.asyncio
async def test_ai_processing_service_uses_cache_before_second_gateway_call(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
) -> None:
    fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    service, _, gateway = build_ai_service(fixture_response=fixture)

    first = await service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["user_profile"],
    )
    second = await service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["user_profile"],
    )

    assert first.model_dump() == second.model_dump()
    assert gateway.invocation_count == 1


@pytest.mark.asyncio
async def test_ai_processing_service_reads_repository_as_durable_cache(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
) -> None:
    fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    first_service, repository, first_gateway = build_ai_service(fixture_response=fixture)
    await first_service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["user_profile"],
    )

    second_gateway = MockModelGateway(fail_with=RuntimeError("should not be called"))
    second_service, _, _ = build_ai_service(gateway=second_gateway, repository=repository)
    cached = await second_service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["user_profile"],
    )

    assert cached.ai_result_id == "ai_001"
    assert first_gateway.invocation_count == 1
    assert second_gateway.invocation_count == 0


@pytest.mark.asyncio
async def test_ai_processing_service_falls_back_and_logs_failure(
    build_ai_service,
    flow_inputs,
) -> None:
    service, repository, _ = build_ai_service(gateway=InvalidJSONGateway())

    result = await service.analyze_or_fallback(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["user_profile"],
    )

    assert result is None
    call_logs = await repository.list_call_logs("evt_001", "stu_001")
    assert len(call_logs) == 1
    assert call_logs[0].status == "failed"
    assert "Expecting value" in call_logs[0].error_message
