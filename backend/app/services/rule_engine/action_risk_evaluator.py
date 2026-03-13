from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.app.services.ingestion.models import SourceEvent

LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class ActionRiskEvaluator:
    async def evaluate(
        self,
        event: SourceEvent,
        signals: dict[str, Any],
        evaluated_rules: list[dict[str, Any]],
        relevance_status: str,
    ) -> dict[str, Any]:
        candidate_categories: list[str] = []
        explanations: list[str] = []
        matched_rules = []

        action_required = bool(signals.get("action_keywords"))
        deadline_at = signals.get("deadline_at")
        urgency_level = "low"
        risk_level = "low"

        for match in evaluated_rules:
            outputs = match["rule"].outputs
            self._extend_unique(candidate_categories, outputs.get("candidate_categories", []))
            if outputs.get("action_required") is True:
                action_required = True
            urgency_level = self._max_level(urgency_level, outputs.get("urgency_level"))
            risk_level = self._max_level(risk_level, outputs.get("risk_level"))
            if outputs.get("emit_match", False) and outputs.get("dimension") in {"action", "deadline", "risk"}:
                matched_rules.append(match["matched_rule"])
            explanation = outputs.get("explanation")
            if explanation and outputs.get("dimension") in {"action", "deadline"}:
                explanations.append(explanation)

        inferred_urgency, inferred_risk = self._infer_levels(
            event=event,
            action_required=action_required,
            deadline_at=deadline_at,
            candidate_categories=candidate_categories,
            relevance_status=relevance_status,
        )
        urgency_level = self._max_level(urgency_level, inferred_urgency)
        risk_level = self._max_level(risk_level, inferred_risk)

        should_continue = relevance_status != "irrelevant" or action_required

        return {
            "candidate_categories": candidate_categories,
            "matched_rules": self._dedupe_rules(matched_rules),
            "action_required": action_required,
            "deadline_at": deadline_at,
            "urgency_level": urgency_level,
            "risk_level": risk_level,
            "explanations": self._dedupe_strings(explanations),
            "should_continue": should_continue,
        }

    def _infer_levels(
        self,
        event: SourceEvent,
        action_required: bool,
        deadline_at: str | None,
        candidate_categories: list[str],
        relevance_status: str,
    ) -> tuple[str, str]:
        if not action_required:
            return ("low", "low" if relevance_status != "relevant" else "medium")

        urgency_level = "medium"
        risk_level = "medium"

        if "graduation" in candidate_categories or "material_submission" in candidate_categories:
            risk_level = "high"

        if deadline_at:
            reference_time = datetime.fromisoformat(event.published_at or event.collected_at)
            deadline_dt = datetime.fromisoformat(deadline_at)
            remaining = deadline_dt - reference_time
            if remaining.days <= 1:
                return ("critical", "critical")
            if remaining.days <= 3:
                return ("high", "high")
            if remaining.days <= 7:
                return ("medium", "high")

        return urgency_level, risk_level

    def _max_level(self, current: str, candidate: str | None) -> str:
        if not candidate:
            return current
        if LEVEL_ORDER[candidate] > LEVEL_ORDER[current]:
            return candidate
        return current

    def _extend_unique(self, target: list[str], values: list[str]) -> None:
        for value in values:
            if value not in target:
                target.append(value)

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            if value and value not in result:
                result.append(value)
        return result

    def _dedupe_rules(self, values: list[Any]) -> list[Any]:
        result = []
        seen: set[str] = set()
        for value in values:
            if value.rule_id in seen:
                continue
            result.append(value)
            seen.add(value.rule_id)
        return result
