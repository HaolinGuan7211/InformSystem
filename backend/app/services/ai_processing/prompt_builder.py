from __future__ import annotations

import json
from pathlib import Path

from backend.app.services.ai_processing.models import AIStage1Result, ProfileContext, RuleAnalysisResult
from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.user_profile.light_profile_tag_builder import LightProfileTags


class PromptBuilder:
    MAX_CONTENT_TEXT_LENGTH = 12000

    def __init__(
        self,
        template_path: Path | None = None,
        prompt_version: str = "prompt_v1",
        stage1_template_path: Path | None = None,
    ) -> None:
        self._template_path = (
            Path(template_path)
            if template_path is not None
            else Path(__file__).resolve().parent / "prompts" / "notice_analysis_v1.txt"
        )
        self._stage1_template_path = (
            Path(stage1_template_path)
            if stage1_template_path is not None
            else Path(__file__).resolve().parent / "prompts" / "notice_analysis_stage1_v1.txt"
        )
        self._prompt_version = prompt_version

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    async def build_stage1(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        light_profile_tags: LightProfileTags,
    ) -> dict[str, object]:
        if not isinstance(light_profile_tags, LightProfileTags):
            payload = (
                light_profile_tags.model_dump()
                if hasattr(light_profile_tags, "model_dump")
                else light_profile_tags
            )
            light_profile_tags = LightProfileTags.model_validate(payload)
        event_payload = self._build_event_prompt_payload(event)
        rule_payload = rule_result.model_dump()
        light_profile_payload = light_profile_tags.model_dump()
        rendered_prompt = self._load_stage1_template().format(
            prompt_version=self._prompt_version,
            event_json=json.dumps(event_payload, ensure_ascii=False, indent=2),
            rule_result_json=json.dumps(rule_payload, ensure_ascii=False, indent=2),
            light_profile_tags_json=json.dumps(light_profile_payload, ensure_ascii=False, indent=2),
        )
        return {
            "prompt_version": self._prompt_version,
            "template_name": self._stage1_template_path.stem,
            "instructions": rendered_prompt,
            "context": {
                "analysis_stage": "stage1",
                "event": event_payload,
                "rule_result": rule_payload,
                "light_profile_tags": light_profile_payload,
            },
            "expected_output_keys": [
                "relevance_hint_stage1",
                "required_profile_facets",
                "reason_summary_stage1",
                "confidence",
            ],
        }

    async def build(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        profile_context: ProfileContext,
        stage1_result: AIStage1Result | None = None,
    ) -> dict[str, object]:
        return await self.build_stage2(
            event=event,
            rule_result=rule_result,
            profile_context=profile_context,
            stage1_result=stage1_result,
        )

    async def build_stage2(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        profile_context: ProfileContext,
        stage1_result: AIStage1Result | None = None,
    ) -> dict[str, object]:
        if not isinstance(profile_context, ProfileContext):
            profile_context = ProfileContext.model_validate(profile_context.model_dump())
        event_payload = self._build_event_prompt_payload(event)
        rule_payload = rule_result.model_dump()
        profile_context_payload = profile_context.model_dump()
        stage1_payload = stage1_result.model_dump() if stage1_result is not None else None
        rendered_prompt = self._load_template().format(
            prompt_version=self._prompt_version,
            event_json=json.dumps(event_payload, ensure_ascii=False, indent=2),
            rule_result_json=json.dumps(rule_payload, ensure_ascii=False, indent=2),
            profile_context_json=json.dumps(profile_context_payload, ensure_ascii=False, indent=2),
            stage1_result_json=json.dumps(stage1_payload, ensure_ascii=False, indent=2),
        )
        return {
            "prompt_version": self._prompt_version,
            "template_name": self._template_path.stem,
            "instructions": rendered_prompt,
            "context": {
                "analysis_stage": "stage2",
                "event": event_payload,
                "rule_result": rule_payload,
                "profile_context": profile_context_payload,
                "stage1_result": stage1_payload,
            },
            "expected_output_keys": [
                "summary",
                "normalized_category",
                "action_items",
                "extracted_fields",
                "relevance_hint",
                "urgency_hint",
                "risk_hint",
                "confidence",
                "needs_human_review",
            ],
        }

    def _load_template(self) -> str:
        return self._template_path.read_text(encoding="utf-8")

    def _load_stage1_template(self) -> str:
        return self._stage1_template_path.read_text(encoding="utf-8")

    def _build_event_prompt_payload(self, event: SourceEvent) -> dict[str, object]:
        payload = event.model_dump()
        content_text = str(payload.get("content_text") or "")
        content_was_truncated = len(content_text) > self.MAX_CONTENT_TEXT_LENGTH
        if content_was_truncated:
            payload["content_text"] = f"{content_text[: self.MAX_CONTENT_TEXT_LENGTH]}\n...[truncated]"
        payload["content_html"] = None

        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            payload["metadata"] = {
                key: metadata[key]
                for key in ("authority_level", "department", "canonical_notice_id", "unique_source_key")
                if key in metadata
            }
            if content_was_truncated:
                payload["metadata"]["content_text_truncated"] = True

        return payload
