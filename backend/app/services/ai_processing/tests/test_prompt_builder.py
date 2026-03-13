from __future__ import annotations

import pytest

from backend.app.services.ai_processing.prompt_builder import PromptBuilder


@pytest.mark.asyncio
async def test_prompt_builder_includes_prompt_version_and_context(ai_test_settings, flow_inputs) -> None:
    builder = PromptBuilder(
        template_path=ai_test_settings.ai_prompt_template_path,
        prompt_version=ai_test_settings.ai_prompt_version,
    )

    prompt = await builder.build(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["user_profile"],
    )

    assert prompt["prompt_version"] == "prompt_v1"
    assert prompt["context"]["event"]["event_id"] == "evt_001"
    assert prompt["context"]["rule_result"]["should_invoke_ai"] is True
    assert prompt["context"]["user_profile"]["user_id"] == "stu_001"
    assert "不要输出最终 decision_action" in prompt["instructions"]
