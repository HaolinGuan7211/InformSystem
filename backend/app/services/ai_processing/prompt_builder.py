from __future__ import annotations

import json
from pathlib import Path

from backend.app.services.ai_processing.models import RuleAnalysisResult, UserProfile
from backend.app.services.ingestion.models import SourceEvent


class PromptBuilder:
    def __init__(self, template_path: Path | None = None, prompt_version: str = "prompt_v1") -> None:
        self._template_path = template_path or Path(__file__).resolve().parent / "prompts" / "notice_analysis_v1.txt"
        self._prompt_version = prompt_version

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    async def build(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        user_profile: UserProfile,
    ) -> dict[str, object]:
        event_payload = event.model_dump()
        rule_payload = rule_result.model_dump()
        user_payload = user_profile.model_dump()
        rendered_prompt = self._load_template().format(
            prompt_version=self._prompt_version,
            event_json=json.dumps(event_payload, ensure_ascii=False, indent=2),
            rule_result_json=json.dumps(rule_payload, ensure_ascii=False, indent=2),
            user_profile_json=json.dumps(user_payload, ensure_ascii=False, indent=2),
        )
        return {
            "prompt_version": self._prompt_version,
            "template_name": self._template_path.stem,
            "instructions": rendered_prompt,
            "context": {
                "event": event_payload,
                "rule_result": rule_payload,
                "user_profile": user_payload,
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
