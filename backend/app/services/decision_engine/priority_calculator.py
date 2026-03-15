from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.app.shared.models import AIAnalysisResult, PriorityLevel, RuleAnalysisResult


class PriorityCalculator:
    _level_weights = {
        "low": 0.0,
        "medium": 10.0,
        "high": 18.0,
        "critical": 28.0,
    }

    async def calculate(
        self,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
        profile_signal_summary: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        decision_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_time = self._resolve_current_time(context, rule_result.generated_at)
        base_relevance_status = str(
            (decision_context or {}).get("base_relevance_status") or rule_result.relevance_status
        )
        effective_relevance_status = str(
            (decision_context or {}).get("effective_relevance_status") or rule_result.relevance_status
        )

        score = self._relevance_weight(rule_result, base_relevance_status)
        if rule_result.action_required:
            score += 15.0

        score += self._level_weights[rule_result.urgency_level]
        score += self._level_weights[rule_result.risk_level]
        score += self._deadline_weight(rule_result.deadline_at, current_time)
        score += self._ai_weight(ai_result, rule_result)
        score += self._profile_signal_weight(profile_signal_summary)
        score = self._apply_force_action_cap(score, decision_context)

        priority_score = float(round(min(max(score, 0.0), 100.0)))
        priority_level = self._map_priority_level(priority_score)

        return {
            "priority_score": priority_score,
            "priority_level": priority_level,
            "relevance_status": effective_relevance_status,
            "action_required": rule_result.action_required,
            "deadline_at": rule_result.deadline_at,
            "should_continue": rule_result.should_continue,
            "profile_signal_bonus": self._profile_signal_weight(profile_signal_summary),
            "current_time": current_time.isoformat(),
        }

    def _resolve_current_time(self, context: dict[str, Any] | None, fallback: str) -> datetime:
        value = (context or {}).get("current_time") or fallback
        return datetime.fromisoformat(value)

    def _relevance_weight(self, rule_result: RuleAnalysisResult, relevance_status: str) -> float:
        if relevance_status == "relevant":
            return rule_result.relevance_score * 35.0
        if relevance_status == "unknown":
            return rule_result.relevance_score * 20.0
        return rule_result.relevance_score * 5.0

    def _deadline_weight(self, deadline_at: str | None, current_time: datetime) -> float:
        if not deadline_at:
            return 0.0

        deadline = datetime.fromisoformat(deadline_at)
        hours_to_deadline = (deadline - current_time).total_seconds() / 3600

        if hours_to_deadline <= 24:
            return 10.0
        if hours_to_deadline <= 72:
            return 7.0
        if hours_to_deadline <= 168:
            return 4.0
        return 2.0

    def _ai_weight(
        self,
        ai_result: AIAnalysisResult | None,
        rule_result: RuleAnalysisResult,
    ) -> float:
        if ai_result is None:
            return 0.0

        if ai_result.needs_human_review:
            return 1.0
        if ai_result.confidence >= 0.8:
            return 5.0
        if ai_result.confidence >= 0.6:
            return 3.0
        if ai_result.relevance_hint and rule_result.relevance_status == "unknown":
            return 2.0
        return 1.0

    def _profile_signal_weight(self, profile_signal_summary: dict[str, Any] | None) -> float:
        if not profile_signal_summary:
            return 0.0
        return float(profile_signal_summary.get("score_bonus", 0.0))

    def _apply_force_action_cap(self, score: float, decision_context: dict[str, Any] | None) -> float:
        force_action = (decision_context or {}).get("force_action")
        if force_action == "ignore":
            return 0.0
        if force_action == "archive":
            return min(score, 20.0)
        if force_action in {"digest", "digest_or_archive"}:
            return min(max(score, 55.0), 74.0)
        return score

    def _map_priority_level(self, score: float) -> PriorityLevel:
        if score >= 90:
            return "critical"
        if score >= 75:
            return "high"
        if score >= 55:
            return "medium"
        return "low"
