from __future__ import annotations

import pytest

from backend.app.services.ai_processing.prompt_builder import PromptBuilder
from backend.app.services.user_profile.light_profile_tag_builder import LightProfileTags


@pytest.mark.asyncio
async def test_prompt_builder_builds_stage1_prompt_with_light_profile_tags(
    ai_test_settings,
    flow_inputs,
) -> None:
    builder = PromptBuilder(
        template_path=ai_test_settings.ai_prompt_template_path,
        prompt_version=ai_test_settings.ai_prompt_version,
    )
    light_profile_tags = LightProfileTags(
        user_id="stu_001",
        college="计算机学院",
        major="软件工程",
        grade="2022",
        degree_level="undergraduate",
        identity_tags=["毕业生"],
        current_course_tags=[],
        current_task_tags=["毕业资格审核"],
        graduation_tags=["graduation_review", "graduating_student"],
        generated_at="2026-03-13T10:22:00+08:00",
    )

    prompt = await builder.build_stage1(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        light_profile_tags,
    )

    assert prompt["prompt_version"] == "prompt_v1"
    assert prompt["context"]["analysis_stage"] == "stage1"
    assert prompt["context"]["light_profile_tags"]["user_id"] == "stu_001"
    assert prompt["context"]["event"]["content_html"] is None
    assert prompt["expected_output_keys"] == [
        "relevance_hint_stage1",
        "required_profile_facets",
        "reason_summary_stage1",
        "confidence",
    ]
    assert "publisher" in prompt["instructions"]
    assert "主题对学生可能有用" in prompt["instructions"]
    assert "公共讲座" in prompt["instructions"]
    assert "required_profile_facets" in prompt["instructions"]


@pytest.mark.asyncio
async def test_prompt_builder_includes_prompt_version_and_stage2_context(
    ai_test_settings,
    flow_inputs,
) -> None:
    builder = PromptBuilder(
        template_path=ai_test_settings.ai_prompt_template_path,
        prompt_version=ai_test_settings.ai_prompt_version,
    )

    prompt = await builder.build(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )

    assert prompt["prompt_version"] == "prompt_v1"
    assert prompt["context"]["analysis_stage"] == "stage2"
    assert prompt["context"]["event"]["event_id"] == "evt_001"
    assert prompt["context"]["event"]["content_html"] is None
    assert prompt["context"]["rule_result"]["should_invoke_ai"] is True
    assert prompt["context"]["profile_context"]["user_id"] == "stu_001"
    assert prompt["context"]["profile_context"]["facets"] == [
        "identity_core",
        "graduation_progress",
    ]
    assert prompt["context"]["stage1_result"] is None
    assert "decision_action" in prompt["instructions"]
    assert "publisher != audience" in prompt["instructions"]
    assert "用户级证据" in prompt["instructions"]
    assert "停水停电" in prompt["instructions"]


@pytest.mark.asyncio
async def test_prompt_builder_strips_large_content_html_and_extra_metadata(
    ai_test_settings,
    flow_inputs,
) -> None:
    builder = PromptBuilder(
        template_path=ai_test_settings.ai_prompt_template_path,
        prompt_version=ai_test_settings.ai_prompt_version,
    )

    event = flow_inputs["event"].model_copy(
        update={
            "content_html": "<div>" + ("x" * 50000) + "</div>",
            "metadata": {
                "authority_level": "high",
                "department": "教务部",
                "ignored_blob": "y" * 1000,
            },
        }
    )

    prompt = await builder.build(
        event,
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )

    assert prompt["context"]["event"]["content_html"] is None
    assert prompt["context"]["event"]["metadata"] == {
        "authority_level": "high",
        "department": "教务部",
    }
    assert "x" * 1000 not in prompt["instructions"]
    assert "ignored_blob" not in prompt["instructions"]
