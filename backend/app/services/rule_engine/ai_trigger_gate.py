from __future__ import annotations

from typing import Any

from backend.app.services.rule_engine.models import RuleAnalysisResult


class AITriggerGate:
    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self._policy = policy or {}

    async def should_invoke_ai(self, analysis: RuleAnalysisResult) -> bool:
        if not analysis.should_continue:
            return False
        if self._policy.get("skip_on_irrelevant", True) and analysis.relevance_status == "irrelevant":
            return False
        if self._policy.get("invoke_on_unknown", True) and analysis.relevance_status == "unknown":
            return True
        if self._policy.get("invoke_on_action_with_deadline", True) and analysis.action_required and analysis.deadline_at:
            return True
        if self._policy.get("invoke_on_high_risk", True) and analysis.risk_level in {"high", "critical"}:
            return True
        return False
