from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Callable

from backend.app.services.ai_processing.models import AIModelConfig, GatewayResponse


class ModelGatewayError(RuntimeError):
    pass


class ModelGateway(ABC):
    @abstractmethod
    async def invoke(self, prompt: dict[str, Any], model_config: AIModelConfig) -> GatewayResponse:
        raise NotImplementedError


class MockModelGateway(ModelGateway):
    def __init__(
        self,
        fixture_responses: dict[str | tuple[str, str], dict[str, Any]] | None = None,
        latency_ms: int = 15,
        fail_with: Exception | None = None,
    ) -> None:
        self._fixture_responses = {
            self._normalize_key(key): value for key, value in (fixture_responses or {}).items()
        }
        self._latency_ms = latency_ms
        self._fail_with = fail_with
        self.invocation_count = 0

    async def invoke(self, prompt: dict[str, Any], model_config: AIModelConfig) -> GatewayResponse:
        self.invocation_count += 1
        if self._fail_with is not None:
            raise ModelGatewayError(str(self._fail_with)) from self._fail_with

        context = prompt.get("context", {})
        event = context.get("event", {}) if isinstance(context, dict) else {}
        user_profile = context.get("user_profile", {}) if isinstance(context, dict) else {}
        event_id = str(event.get("event_id", "unknown"))
        user_id = str(user_profile.get("user_id", "unknown"))
        fixture = self._fixture_responses.get(f"{event_id}:{user_id}")
        payload = fixture or self._build_heuristic_payload(context)
        content = payload.get("output", payload)

        return GatewayResponse(
            provider="mock",
            model_name=model_config.model_name,
            content=content,
            raw_request_ref=str(payload.get("raw_request_ref", f"mock_req_{event_id}_{user_id}")),
            raw_response_ref=str(payload.get("raw_response_ref", f"mock_resp_{event_id}_{user_id}")),
            latency_ms=int(payload.get("latency_ms", self._latency_ms)),
            metadata=dict(payload.get("metadata", {})),
        )

    def _build_heuristic_payload(self, context: dict[str, Any]) -> dict[str, Any]:
        event = context.get("event", {})
        rule_result = context.get("rule_result", {})
        user_profile = context.get("user_profile", {})
        text = str(event.get("content_text", "")).strip()
        identity_tags = [
            str(tag).strip()
            for tag in user_profile.get("identity_tags", [])
            if isinstance(tag, str) and tag.strip()
        ]
        audience_values = identity_tags or rule_result.get("extracted_signals", {}).get("audience", [])
        audience_text = self._normalize_audience(audience_values)
        deadline_at = rule_result.get("deadline_at")
        normalized_category = self._resolve_category(text, rule_result)
        output: dict[str, Any] = {
            "summary": self._resolve_summary(text, audience_text, deadline_at),
            "normalized_category": normalized_category,
            "action_items": self._resolve_action_items(text),
            "extracted_fields": [],
            "relevance_hint": self._resolve_relevance_hint(audience_text),
            "urgency_hint": "存在明确截止时间" if deadline_at else None,
            "risk_hint": self._resolve_risk_hint(normalized_category, rule_result),
            "confidence": min(max(float(rule_result.get("relevance_score", 0.0)), 0.0), 1.0),
            "needs_human_review": rule_result.get("relevance_status") == "unknown",
        }
        if deadline_at:
            output["extracted_fields"] = [
                {
                    "field_name": "deadline_at",
                    "field_value": deadline_at,
                    "confidence": 0.94,
                }
            ]

        return {
            "output": output,
            "raw_request_ref": f"mock_req_{event.get('event_id', 'unknown')}_{user_profile.get('user_id', 'unknown')}",
            "raw_response_ref": f"mock_resp_{event.get('event_id', 'unknown')}_{user_profile.get('user_id', 'unknown')}",
            "latency_ms": self._latency_ms,
        }

    @staticmethod
    def _normalize_key(key: str | tuple[str, str]) -> str:
        if isinstance(key, tuple):
            return f"{key[0]}:{key[1]}"
        return key

    @staticmethod
    def _normalize_audience(values: list[Any]) -> str:
        audience_items = [str(item).strip() for item in values if str(item).strip()]
        if not audience_items:
            return ""
        normalized: list[str] = []
        for item in audience_items:
            cleaned = item
            if cleaned.endswith("毕业生") and cleaned not in {"毕业生", "相关毕业生"}:
                cleaned = "毕业生"
            if cleaned not in normalized:
                normalized.append(cleaned)
        return "、".join(normalized)

    def _resolve_summary(self, text: str, audience_text: str, deadline_at: Any) -> str | None:
        deadline_text = self._format_deadline(deadline_at)
        if "毕业资格审核材料" in text and deadline_text:
            audience = audience_text or "相关学生"
            return f"该通知要求{audience}在{deadline_text}提交毕业资格审核材料。"
        return text[:120] if text else None

    @staticmethod
    def _resolve_action_items(text: str) -> list[str]:
        if "毕业资格审核材料" in text:
            return ["提交毕业资格审核材料"]
        if "提交" in text:
            return [text.replace("请", "").strip("。")]
        return []

    @staticmethod
    def _resolve_relevance_hint(audience_text: str) -> str | None:
        if audience_text:
            return f"面向{audience_text}，与你当前身份高度相关"
        return "与当前用户画像存在一定相关性"

    @staticmethod
    def _resolve_category(text: str, rule_result: dict[str, Any]) -> str | None:
        candidate_categories = [str(item) for item in rule_result.get("candidate_categories", [])]
        if "graduation" in candidate_categories and "material_submission" in candidate_categories:
            return "graduation_material_submission"
        if "毕业" in text and "材料" in text:
            return "graduation_material_submission"
        if candidate_categories:
            return candidate_categories[0]
        return None

    @staticmethod
    def _resolve_risk_hint(normalized_category: str | None, rule_result: dict[str, Any]) -> str | None:
        if normalized_category == "graduation_material_submission":
            return "错过可能影响毕业审核进度"
        risk_level = str(rule_result.get("risk_level", "")).lower()
        if risk_level in {"high", "critical"}:
            return "错过可能带来较高业务风险"
        return None

    @staticmethod
    def _format_deadline(deadline_at: Any) -> str | None:
        if not isinstance(deadline_at, str) or len(deadline_at) < 10:
            return None
        try:
            month = int(deadline_at[5:7])
            day = int(deadline_at[8:10])
        except ValueError:
            return None
        return f"{month}月{day}日前"


class HTTPModelGateway(ModelGateway):
    def __init__(
        self,
        endpoint: str | None,
        api_key: str | None = None,
        transport: Callable[[dict[str, Any], AIModelConfig], dict[str, Any]] | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._transport = transport

    async def invoke(self, prompt: dict[str, Any], model_config: AIModelConfig) -> GatewayResponse:
        if not self._endpoint and self._transport is None:
            raise ModelGatewayError("HTTP model gateway requires an endpoint or transport")

        request_payload = {
            "prompt": prompt,
            "model_config": model_config.model_dump(exclude_none=True),
        }
        started_at = time.perf_counter()
        try:
            if self._transport is not None:
                response_payload = await asyncio.to_thread(self._transport, request_payload, model_config)
            else:
                response_payload = await asyncio.to_thread(self._post_json, request_payload, model_config)
        except Exception as exc:
            raise ModelGatewayError(f"Model gateway request failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        output = response_payload.get("output", response_payload)
        return GatewayResponse(
            provider=str(response_payload.get("provider", model_config.provider)),
            model_name=str(response_payload.get("model_name", model_config.model_name)),
            content=output,
            raw_request_ref=response_payload.get("raw_request_ref"),
            raw_response_ref=response_payload.get("raw_response_ref"),
            latency_ms=int(response_payload.get("latency_ms", latency_ms)),
            metadata=dict(response_payload.get("metadata", {})),
        )

    def _post_json(self, payload: dict[str, Any], model_config: AIModelConfig) -> dict[str, Any]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=model_config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise ModelGatewayError(f"Unable to reach model gateway: {exc}") from exc
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ModelGatewayError("Model gateway returned non-JSON payload") from exc
        if not isinstance(parsed, dict):
            raise ModelGatewayError("Model gateway returned a non-object JSON payload")
        return parsed
