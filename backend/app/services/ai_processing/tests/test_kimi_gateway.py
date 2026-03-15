from __future__ import annotations

import pytest

from backend.app.services.ai_processing.model_gateway import KimiChatGateway
from backend.app.services.ai_processing.models import AIModelConfig


def build_transport_response(content: str | dict) -> dict:
    return {
        "id": "chatcmpl_kimi_001",
        "model": "moonshot-v1-8k",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                },
            }
        ],
        "usage": {
            "prompt_tokens": 123,
            "completion_tokens": 45,
            "total_tokens": 168,
        },
    }


@pytest.mark.asyncio
async def test_kimi_gateway_builds_openai_compatible_request() -> None:
    captured: dict[str, object] = {}

    def transport(payload, model_config):
        captured["payload"] = payload
        captured["model_config"] = model_config
        return build_transport_response(
            {
                "summary": "需要尽快关注的通知",
                "normalized_category": "student_opportunity",
                "action_items": ["报名"],
                "extracted_fields": [],
                "relevance_hint": "与当前学生身份相关",
                "urgency_hint": "建议近期处理",
                "risk_hint": "错过可能失去报名机会",
                "confidence": 0.86,
                "needs_human_review": False,
            }
        )

    gateway = KimiChatGateway(
        base_url="https://api.moonshot.cn/v1",
        api_key="test-key",
        transport=transport,
    )
    prompt = {
        "instructions": "Return a JSON object only.",
        "prompt_version": "prompt_v1",
    }
    model_config = AIModelConfig(
        provider="kimi",
        model_name="moonshot-v1-8k",
        prompt_version="prompt_v1",
    )

    response = await gateway.invoke(prompt, model_config)

    payload = captured["payload"]
    assert payload["model"] == "moonshot-v1-8k"
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["content"] == "Return a JSON object only."
    assert payload["response_format"] == {"type": "json_object"}
    assert response.provider == "kimi"
    assert response.model_name == "moonshot-v1-8k"
    assert response.content["normalized_category"] == "student_opportunity"
    assert response.metadata["usage"]["total_tokens"] == 168


@pytest.mark.asyncio
async def test_kimi_gateway_strips_markdown_code_fences() -> None:
    gateway = KimiChatGateway(
        base_url="https://api.moonshot.cn/v1",
        api_key="test-key",
        transport=lambda payload, model_config: build_transport_response(
            """```json
            {
              "summary": "结构化输出",
              "normalized_category": "student_opportunity",
              "action_items": ["报名"],
              "extracted_fields": [],
              "relevance_hint": "相关",
              "urgency_hint": "较高",
              "risk_hint": "可能错过机会",
              "confidence": 0.78,
              "needs_human_review": false
            }
            ```"""
        ),
    )

    response = await gateway.invoke(
        {"instructions": "Return JSON only."},
        AIModelConfig(
            provider="kimi",
            model_name="moonshot-v1-8k",
            prompt_version="prompt_v1",
        ),
    )

    assert response.content["summary"] == "结构化输出"


@pytest.mark.asyncio
async def test_kimi_thinking_model_disables_json_mode() -> None:
    captured: dict[str, object] = {}

    def transport(payload, model_config):
        captured["payload"] = payload
        return build_transport_response("{}")

    gateway = KimiChatGateway(
        base_url="https://api.moonshot.cn/v1",
        api_key="test-key",
        transport=transport,
    )
    await gateway.invoke(
        {"instructions": "Return JSON only."},
        AIModelConfig(
            provider="kimi",
            model_name="kimi-thinking-preview",
            prompt_version="prompt_v1",
        ),
    )

    payload = captured["payload"]
    assert "response_format" not in payload


@pytest.mark.asyncio
async def test_kimi_k2_thinking_model_disables_json_mode() -> None:
    captured: dict[str, object] = {}

    def transport(payload, model_config):
        captured["payload"] = payload
        return build_transport_response("{}")

    gateway = KimiChatGateway(
        base_url="https://api.moonshot.cn/v1",
        api_key="test-key",
        transport=transport,
    )
    await gateway.invoke(
        {"instructions": "Return JSON only."},
        AIModelConfig(
            provider="kimi",
            model_name="kimi-k2-thinking",
            prompt_version="prompt_v1",
        ),
    )

    payload = captured["payload"]
    assert "response_format" not in payload
