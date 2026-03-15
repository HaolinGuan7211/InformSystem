from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from backend.app.shared.models import AIAnalysisResult, DecisionResult, RuleAnalysisResult, SourceEvent, UserProfile
from backend.app.services.decision_engine.action_resolver import ActionResolver
from backend.app.services.decision_engine.channel_resolver import ChannelResolver
from backend.app.services.decision_engine.evidence_aggregator import EvidenceAggregator
from backend.app.services.decision_engine.policy_loader import PolicyLoader
from backend.app.services.decision_engine.profile_signal_resolver import ProfileSignalResolver
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
        profile_signal_resolver: ProfileSignalResolver | None = None,
        timezone_offset: str = "+08:00",
    ) -> None:
        self._policy_loader = policy_loader
        self._evidence_aggregator = evidence_aggregator
        self._priority_calculator = priority_calculator
        self._action_resolver = action_resolver
        self._channel_resolver = channel_resolver
        self._decision_repository = decision_repository
        self._profile_signal_resolver = profile_signal_resolver or ProfileSignalResolver()
        self._timezone_offset = timezone_offset

    async def decide(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None = None,
        context: dict[str, Any] | None = None,
    ) -> DecisionResult:
        profile_signal_summary = await self._profile_signal_resolver.evaluate(
            event=event,
            user_profile=user_profile,
            rule_result=rule_result,
            ai_result=ai_result,
        )
        decision_context = self._build_decision_context(
            event=event,
            user_profile=user_profile,
            rule_result=rule_result,
            ai_result=ai_result,
            profile_signal_summary=profile_signal_summary,
        )
        effective_rule_result = rule_result.model_copy(
            update={
                "relevance_status": decision_context["effective_relevance_status"],
                "should_continue": decision_context["effective_should_continue"],
            }
        )
        policies = await self._policy_loader.load_policies()
        priority = await self._priority_calculator.calculate(
            effective_rule_result,
            ai_result,
            profile_signal_summary=profile_signal_summary,
            context=context,
            decision_context=decision_context,
        )
        action_resolution = await self._action_resolver.resolve(
            event,
            user_profile,
            effective_rule_result,
            priority,
            policies,
            decision_context=decision_context,
        )
        channel_plan = await self._channel_resolver.resolve(
            action_resolution["decision_action"],
            user_profile,
            policies,
            matched_policy=action_resolution["matched_policy"],
            priority_level=priority["priority_level"],
            context=context,
        )
        evidences = await self._evidence_aggregator.aggregate(
            rule_result,
            ai_result,
            user_profile,
            profile_signal_summary=profile_signal_summary,
            decision_context=decision_context,
        )

        policy_version = (context or {}).get("policy_version") or action_resolution["policy_version"]
        generated_at = (context or {}).get("generated_at") or self._default_timestamp()
        decision_id = (context or {}).get("decision_id") or self._build_decision_id(
            event.event_id,
            user_profile.user_id,
            policy_version,
            generated_at,
        )

        metadata: dict[str, Any] = {}
        metadata.update(channel_plan["metadata"])
        if ai_result is None and rule_result.should_invoke_ai:
            metadata["ai_degraded"] = True
        if profile_signal_summary["matched_attention_signals"] or profile_signal_summary["matched_pending_items"]:
            metadata["profile_signal_matches"] = {
                "attention_signal_keys": [
                    str(signal.get("signal_key") or signal.get("signal_type") or "")
                    for signal in profile_signal_summary["matched_attention_signals"]
                ],
                "pending_item_ids": [
                    str(item.get("item_id") or item.get("title") or "")
                    for item in profile_signal_summary["matched_pending_items"]
                ],
            }

        result = DecisionResult(
            decision_id=decision_id,
            event_id=event.event_id,
            user_id=user_profile.user_id,
            relevance_status=decision_context["effective_relevance_status"],
            priority_score=priority["priority_score"],
            priority_level=priority["priority_level"],
            decision_action=action_resolution["decision_action"],
            delivery_timing=channel_plan["delivery_timing"],
            delivery_channels=channel_plan["delivery_channels"],
            action_required=rule_result.action_required,
            deadline_at=rule_result.deadline_at,
            reason_summary=self._build_reason_summary(
                event,
                rule_result,
                ai_result,
                profile_signal_summary,
                decision_action=action_resolution["decision_action"],
                decision_context=decision_context,
            ),
            explanations=self._build_explanations(
                rule_result,
                ai_result,
                profile_signal_summary,
                decision_context=decision_context,
            ),
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
        profile_signal_summary: dict[str, Any] | None,
        decision_action: str,
        decision_context: dict[str, Any],
    ) -> str:
        reason_code = str(decision_context.get("reason_code") or "")
        effective_relevance_status = str(
            decision_context.get("effective_relevance_status") or rule_result.relevance_status
        )

        if reason_code == "rule_irrelevant":
            return "规则层判定该通知与当前用户无关，结束当前处理链路。"
        if reason_code == "ai_stage1_irrelevant":
            return "规则粗筛命中候选范围，但 AI 第一阶段粗筛判定当前通知与用户无关，已归档观察。"
        if reason_code == "ai_stage2_irrelevant":
            return "规则粗筛命中候选范围，但 AI 第二阶段精筛判定当前通知与用户无关，已归档观察。"
        if reason_code == "ai_uncertain_digest":
            retention_reason = str(decision_context.get("uncertain_retention_reason") or "").strip()
            if retention_reason:
                return f"规则粗筛命中候选范围，且可能值得保留关注（{retention_reason}），但 AI 未确认达到强触达阈值，已进入汇总提醒。"
            return "规则粗筛命中候选范围，且可能值得保留关注，但 AI 未确认达到强触达阈值，已进入汇总提醒。"
        if reason_code == "ai_uncertain_archive":
            return "规则粗筛命中候选范围，但 AI 未确认达到保留关注阈值，已归档观察。"
        if reason_code == "ai_missing_candidate":
            if decision_action == "digest":
                return "规则粗筛命中候选范围，但当前缺少 AI 精筛结果，已按保守策略进入汇总提醒。"
            return "规则粗筛命中候选范围，但当前缺少 AI 精筛结果，已按保守策略归档观察。"

        notice_label = self._resolve_notice_label(event, rule_result, ai_result)
        reasons = [notice_label]

        if self._has_profile_signal_match(profile_signal_summary):
            reasons.append("与你当前画像缺口匹配")
        elif reason_code == "ai_confirmed_relevant":
            reasons.append("经 AI 精筛确认与你相关")
        elif effective_relevance_status == "relevant":
            reasons.append("与你身份匹配")

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
        profile_signal_summary: dict[str, Any] | None,
        decision_context: dict[str, Any],
    ) -> list[str]:
        explanations: list[str] = []
        reason_code = str(decision_context.get("reason_code") or "")

        if reason_code == "rule_irrelevant":
            explanations.append("规则层判定与当前用户无关")
        elif rule_result.relevance_status == "relevant":
            if rule_result.relevance_score >= 0.85:
                explanations.append("规则层判定高度相关")
            else:
                explanations.append("规则层判定与当前用户相关")
        else:
            explanations.append("规则层判定存在相关性线索")

        if reason_code == "ai_stage1_irrelevant":
            explanations.append("AI 第一阶段粗筛判定当前通知与用户无关")
        elif reason_code == "ai_stage2_irrelevant":
            explanations.append("AI 第二阶段精筛判定当前通知与用户无关")
        elif reason_code == "ai_uncertain_digest":
            explanations.append("AI 第二阶段精筛未确认达到强触达阈值，但仍保留为汇总关注")
            retention_reason = str(decision_context.get("uncertain_retention_reason") or "").strip()
            if retention_reason:
                explanations.append(f"保留 digest 的原因：{retention_reason}")
        elif reason_code == "ai_uncertain_archive":
            explanations.append("AI 第二阶段精筛未确认达到保留关注阈值，按归档处理")
        elif reason_code == "ai_missing_candidate":
            explanations.append("当前缺少 AI 精筛结果，按保守策略处理")
        elif reason_code == "ai_confirmed_relevant":
            explanations.append("AI 精筛确认与当前用户相关")

        if rule_result.action_required:
            explanations.append("存在明确动作要求")

        if rule_result.deadline_at:
            explanations.append("存在明确截止时间")

        if (profile_signal_summary or {}).get("matched_attention_signals"):
            explanations.append("命中画像 attention_signals 中的结构化缺口信号")

        if (profile_signal_summary or {}).get("matched_pending_items"):
            explanations.append("命中画像 pending_items 中的待处理缺口项")

        if ai_result and ai_result.risk_hint:
            explanations.append("AI 补充判断错过风险较高")
        elif (
            ai_result is None
            and rule_result.should_invoke_ai
            and reason_code not in {"ai_missing_candidate", "rule_irrelevant"}
        ):
            explanations.append("AI 不可用时按规则结果降级决策")

        return explanations

    def _has_profile_signal_match(self, profile_signal_summary: dict[str, Any] | None) -> bool:
        if not profile_signal_summary:
            return False
        return bool(
            profile_signal_summary.get("matched_attention_signals")
            or profile_signal_summary.get("matched_pending_items")
        )

    def _build_decision_id(
        self,
        event_id: str,
        user_id: str,
        policy_version: str,
        generated_at: str,
    ) -> str:
        payload = f"{event_id}:{user_id}:{policy_version}:{generated_at}:{uuid4().hex}".encode("utf-8")
        return f"dec_{hashlib.sha1(payload).hexdigest()[:12]}"

    def _default_timestamp(self) -> str:
        offset = self._parse_timezone_offset(self._timezone_offset)
        return datetime.now(timezone.utc).astimezone(offset).isoformat()

    def _parse_timezone_offset(self, value: str) -> timezone:
        sign = 1 if value.startswith("+") else -1
        hour_text, minute_text = value[1:].split(":", maxsplit=1)
        delta = timedelta(hours=int(hour_text), minutes=int(minute_text))
        return timezone(sign * delta)

    def _build_decision_context(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
        profile_signal_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rule_relevance_status = rule_result.relevance_status
        ai_hint = str(ai_result.relevance_hint or "").strip().lower() if ai_result else None
        ai_stage = self._resolve_ai_stage(ai_result)
        has_hard_rule_positive = self._has_hard_rule_positive_match(rule_result, user_profile)

        context = {
            "base_relevance_status": rule_relevance_status,
            "effective_relevance_status": rule_relevance_status,
            "effective_should_continue": rule_result.should_continue,
            "force_action": None,
            "reason_code": "rule_relevant" if rule_relevance_status == "relevant" else "rule_candidate",
            "ai_stage": ai_stage,
            "ai_relevance_hint": ai_hint,
            "has_hard_rule_positive": has_hard_rule_positive,
        }

        if not rule_result.should_continue or rule_relevance_status == "irrelevant":
            context.update(
                {
                    "effective_relevance_status": "irrelevant",
                    "effective_should_continue": False,
                    "force_action": "ignore",
                    "reason_code": "rule_irrelevant",
                }
            )
            return context

        if ai_hint == "irrelevant":
            if rule_relevance_status == "relevant" and has_hard_rule_positive:
                context["reason_code"] = "rule_relevant"
                return context
            context.update(
                {
                    "effective_relevance_status": "irrelevant",
                    "effective_should_continue": True,
                    "force_action": "archive",
                    "reason_code": "ai_stage1_irrelevant" if ai_stage == "stage1" else "ai_stage2_irrelevant",
                }
            )
            return context

        if ai_hint == "uncertain":
            uncertain_action, retention_reason = self._resolve_uncertain_action(
                event=event,
                user_profile=user_profile,
                rule_result=rule_result,
                ai_result=ai_result,
                profile_signal_summary=profile_signal_summary,
            )
            context.update(
                {
                    "effective_relevance_status": "unknown",
                    "effective_should_continue": True,
                    "force_action": uncertain_action,
                    "reason_code": "ai_uncertain_digest" if uncertain_action == "digest" else "ai_uncertain_archive",
                    "uncertain_retention_reason": retention_reason,
                }
            )
            return context

        if ai_hint == "relevant":
            if rule_relevance_status == "unknown":
                context.update(
                    {
                        "effective_relevance_status": "relevant",
                        "effective_should_continue": True,
                        "reason_code": "ai_confirmed_relevant",
                    }
                )
            return context

        if rule_relevance_status == "unknown":
            context.update(
                {
                    "effective_relevance_status": "unknown",
                    "effective_should_continue": True,
                    "force_action": "digest_or_archive",
                    "reason_code": "ai_missing_candidate" if rule_result.should_invoke_ai else "rule_candidate",
                }
            )

        return context

    def _resolve_uncertain_action(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
        profile_signal_summary: dict[str, Any] | None,
    ) -> tuple[str, str | None]:
        if self._has_profile_signal_match(profile_signal_summary):
            return "digest", "命中当前画像缺口或待处理事项"

        if self._matches_current_task(event, user_profile, ai_result):
            return "digest", "与当前任务存在弱相关线索"

        if self._is_open_opportunity_with_deadline(rule_result, ai_result):
            return "digest", "开放机会且存在明确截止时间"

        if self._is_student_life_impact_notice(event, ai_result):
            return "digest", "公共服务对学生日常生活影响较强"

        return "archive", None

    def _resolve_ai_stage(self, ai_result: AIAnalysisResult | None) -> str | None:
        if ai_result is None:
            return None
        value = ai_result.metadata.get("analysis_stage")
        if not isinstance(value, str):
            return None
        cleaned = value.strip().lower()
        return cleaned or None

    def _has_hard_rule_positive_match(
        self,
        rule_result: RuleAnalysisResult,
        user_profile: UserProfile,
    ) -> bool:
        if rule_result.relevance_status != "relevant":
            return False

        extracted_signals = rule_result.extracted_signals or {}
        audience_values = self._normalize_signal_values(
            extracted_signals.get("explicit_audience") or extracted_signals.get("audience")
        )
        identity_tags = {str(tag).strip() for tag in user_profile.identity_tags if str(tag).strip()}

        if identity_tags.intersection(audience_values):
            return True
        if user_profile.college and user_profile.college in audience_values:
            return True
        if user_profile.major and user_profile.major in audience_values:
            return True
        if user_profile.grade and user_profile.grade in audience_values:
            return True

        course_values = self._normalize_signal_values(extracted_signals.get("courses"))
        for course in user_profile.enrolled_courses:
            if course.course_name and course.course_name in course_values:
                return True

        matched_rule_dimensions = {
            str(rule.dimension).strip()
            for rule in rule_result.matched_rules
            if str(rule.dimension).strip()
        }
        return "audience" in matched_rule_dimensions

    def _normalize_signal_values(self, value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, list):
            return {str(item).strip() for item in value if str(item).strip()}
        cleaned = str(value).strip()
        return {cleaned} if cleaned else set()

    def _matches_current_task(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        ai_result: AIAnalysisResult | None,
    ) -> bool:
        normalized_text = self._normalize_text(
            event.title,
            event.content_text,
            ai_result.summary if ai_result else None,
        )
        if not normalized_text:
            return False

        for task in user_profile.current_tasks:
            cleaned = str(task).strip().lower()
            if len(cleaned) >= 2 and cleaned in normalized_text:
                return True
        return False

    def _is_open_opportunity_with_deadline(
        self,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
    ) -> bool:
        categories = set(rule_result.candidate_categories)
        normalized_category = str(ai_result.normalized_category or "").strip().lower() if ai_result else ""
        open_opportunity_markers = {"open_opportunity", "student_opportunity"}

        if not rule_result.deadline_at:
            return False

        return bool(categories.intersection(open_opportunity_markers) or normalized_category in open_opportunity_markers)

    def _is_student_life_impact_notice(
        self,
        event: SourceEvent,
        ai_result: AIAnalysisResult | None,
    ) -> bool:
        normalized_text = self._normalize_text(
            event.title,
            event.content_text,
            ai_result.summary if ai_result else None,
            ai_result.normalized_category if ai_result else None,
        )
        if not normalized_text:
            return False

        impact_keywords = (
            "停水",
            "停电",
            "停气",
            "停网",
            "断网",
            "宿舍",
            "门禁",
            "校车",
            "食堂",
            "闭馆",
            "楼宇封闭",
        )
        return any(keyword in normalized_text for keyword in impact_keywords)

    def _normalize_text(self, *parts: Any) -> str:
        normalized_parts = [str(part).strip().lower() for part in parts if part not in (None, "", [])]
        return " ".join(part for part in normalized_parts if part)
