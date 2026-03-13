from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.shared.models import AIAnalysisResult, DecisionResult, RuleAnalysisResult, SourceEvent, UserProfile
from backend.app.services.decision_engine.action_resolver import ActionResolver
from backend.app.services.decision_engine.channel_resolver import ChannelResolver
from backend.app.services.decision_engine.evidence_aggregator import EvidenceAggregator
from backend.app.services.decision_engine.policy_loader import PolicyLoader
from backend.app.services.decision_engine.priority_calculator import PriorityCalculator
from backend.app.services.decision_engine.repositories.decision_repository import SQLiteDecisionRepository


class DecisionEngineService:
    def __init__(
        self,
        policy_loader: PolicyLoader,
        evidence_aggregator: EvidenceAggregator,
        priority_calculator: PriorityCalculator,
        action_resolver: ActionResolver,
        channel_resolver: ChannelResolver,
        decision_repository: SQLiteDecisionRepository,
        timezone_offset: str = "+08:00",
    ) -> None:
        self._policy_loader = policy_loader
        self._evidence_aggregator = evidence_aggregator
        self._priority_calculator = priority_calculator
        self._action_resolver = action_resolver
        self._channel_resolver = channel_resolver
        self._decision_repository = decision_repository
        self._timezone_offset = timezone_offset

    async def decide(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None = None,
        context: dict[str, Any] | None = None,
    ) -> DecisionResult:
        policies = await self._policy_loader.load_policies()
        priority = await self._priority_calculator.calculate(rule_result, ai_result, context=context)
        action_resolution = await self._action_resolver.resolve(
            event,
            user_profile,
            rule_result,
            priority,
            policies,
        )
        channel_plan = await self._channel_resolver.resolve(
            action_resolution["decision_action"],
            user_profile,
            policies,
            matched_policy=action_resolution["matched_policy"],
            priority_level=priority["priority_level"],
            context=context,
        )
        evidences = await self._evidence_aggregator.aggregate(rule_result, ai_result, user_profile)

        policy_version = (context or {}).get("policy_version") or action_resolution["policy_version"]
        generated_at = (context or {}).get("generated_at") or self._default_timestamp()
        decision_id = (context or {}).get("decision_id") or self._build_decision_id(
            event.event_id,
            user_profile.user_id,
            policy_version,
        )

        metadata: dict[str, Any] = {}
        metadata.update(channel_plan["metadata"])
        if ai_result is None and rule_result.should_invoke_ai:
            metadata["ai_degraded"] = True

        result = DecisionResult(
            decision_id=decision_id,
            event_id=event.event_id,
            user_id=user_profile.user_id,
            relevance_status=rule_result.relevance_status,
            priority_score=priority["priority_score"],
            priority_level=priority["priority_level"],
            decision_action=action_resolution["decision_action"],
            delivery_timing=channel_plan["delivery_timing"],
            delivery_channels=channel_plan["delivery_channels"],
            action_required=rule_result.action_required,
            deadline_at=rule_result.deadline_at,
            reason_summary=self._build_reason_summary(event, rule_result, ai_result),
            explanations=self._build_explanations(rule_result, ai_result),
            evidences=evidences,
            policy_version=policy_version,
            metadata=metadata,
            generated_at=generated_at,
        )

        await self._decision_repository.save(result)
        return result

    async def decide_batch(
        self,
        inputs: list[tuple[SourceEvent, UserProfile, RuleAnalysisResult, AIAnalysisResult | None]],
        context: dict[str, Any] | None = None,
    ) -> list[DecisionResult]:
        results: list[DecisionResult] = []
        for event, user_profile, rule_result, ai_result in inputs:
            results.append(
                await self.decide(
                    event=event,
                    user_profile=user_profile,
                    rule_result=rule_result,
                    ai_result=ai_result,
                    context=context,
                )
            )
        return results

    def _build_reason_summary(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
    ) -> str:
        if not rule_result.should_continue or rule_result.relevance_status == "irrelevant":
            return "规则层判定该通知与当前用户无关，结束当前处理链路。"

        notice_label = self._resolve_notice_label(event, rule_result, ai_result)
        reasons = [notice_label]

        if rule_result.relevance_status == "relevant":
            reasons.append("与你身份匹配")
        elif rule_result.relevance_status == "unknown":
            reasons.append("与你可能相关")

        if rule_result.deadline_at:
            reasons.append("且存在明确截止时间")
        elif rule_result.action_required:
            reasons.append("且需要及时处理")

        summary = "，".join(reasons)
        return summary if summary.endswith("。") else f"{summary}。"

    def _resolve_notice_label(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
    ) -> str:
        combined_categories = set(rule_result.candidate_categories)
        normalized_category = ai_result.normalized_category if ai_result else None

        if normalized_category == "graduation_material_submission" or {
            "graduation",
            "material_submission",
        }.issubset(combined_categories):
            return "毕业审核材料提交通知"

        category_labels = {
            "course_schedule_change": "课程安排调整通知",
            "graduation": "毕业相关通知",
            "material_submission": "材料提交通知",
            "credit": "学分相关通知",
            "exam": "考试相关通知",
        }

        if normalized_category and normalized_category in category_labels:
            return category_labels[normalized_category]

        for category in rule_result.candidate_categories:
            if category in category_labels:
                return category_labels[category]

        if event.title:
            return event.title

        return "该通知"

    def _build_explanations(
        self,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
    ) -> list[str]:
        explanations: list[str] = []

        if rule_result.relevance_status == "relevant":
            if rule_result.relevance_score >= 0.85:
                explanations.append("规则层判定高度相关")
            else:
                explanations.append("规则层判定与当前用户相关")
        elif rule_result.relevance_status == "unknown":
            explanations.append("规则层判定存在相关性线索")
        else:
            explanations.append("规则层判定与当前用户无关")

        if rule_result.action_required:
            explanations.append("存在明确动作要求")

        if rule_result.deadline_at:
            explanations.append("存在明确截止时间")

        if ai_result and ai_result.risk_hint:
            explanations.append("AI 补充判断错过风险较高")
        elif ai_result is None and rule_result.should_invoke_ai:
            explanations.append("AI 不可用时按规则结果降级决策")

        return explanations

    def _build_decision_id(self, event_id: str, user_id: str, policy_version: str) -> str:
        payload = f"{event_id}:{user_id}:{policy_version}".encode("utf-8")
        return f"dec_{hashlib.sha1(payload).hexdigest()[:12]}"

    def _default_timestamp(self) -> str:
        offset = self._parse_timezone_offset(self._timezone_offset)
        return datetime.now(timezone.utc).astimezone(offset).isoformat()

    def _parse_timezone_offset(self, value: str) -> timezone:
        sign = 1 if value.startswith("+") else -1
        hour_text, minute_text = value[1:].split(":", maxsplit=1)
        delta = timedelta(hours=int(hour_text), minutes=int(minute_text))
        return timezone(sign * delta)
