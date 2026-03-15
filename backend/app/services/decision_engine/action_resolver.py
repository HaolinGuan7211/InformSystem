from __future__ import annotations

from typing import Any

from backend.app.shared.models import RuleAnalysisResult, SourceEvent, UserProfile
from backend.app.services.decision_engine.policies import PushPolicyConfig


class ActionResolver:
    async def resolve(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        rule_result: RuleAnalysisResult,
        priority: dict[str, Any],
        policies: list[PushPolicyConfig],
        decision_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        forced_action = self._resolve_forced_action(user_profile, decision_context)
        if forced_action is not None:
            return self._build_result(forced_action, self._find_action_policy(forced_action, policies), policies)

        if not priority["should_continue"]:
            return self._build_result("ignore", None, policies)

        if priority["relevance_status"] == "irrelevant":
            return self._build_result("ignore", self._find_action_policy("ignore", policies), policies)

        if (
            (decision_context or {}).get("reason_code") == "ai_confirmed_relevant"
            and priority["priority_level"] == "low"
        ):
            action = "digest" if user_profile.notification_preference.digest_enabled else "archive"
            return self._build_result(action, self._find_action_policy(action, policies), policies)

        if self._is_muted(rule_result, user_profile) and priority["priority_level"] in {"low", "medium"}:
            return self._build_result("archive", self._find_action_policy("archive", policies), policies)

        matched_policy = self._match_policy(priority, rule_result, user_profile, policies)
        action = matched_policy.action if matched_policy else self._fallback_action(priority, user_profile)

        if action == "digest" and not user_profile.notification_preference.digest_enabled:
            matched_policy = self._find_action_policy("archive", policies)
            action = "archive"

        return self._build_result(action, matched_policy, policies)

    def _build_result(
        self,
        action: str,
        policy: PushPolicyConfig | None,
        policies: list[PushPolicyConfig],
    ) -> dict[str, Any]:
        policy_version = policy.version if policy else (policies[0].version if policies else "policy_v1")
        return {
            "decision_action": action,
            "matched_policy": policy,
            "policy_version": policy_version,
        }

    def _match_policy(
        self,
        priority: dict[str, Any],
        rule_result: RuleAnalysisResult,
        user_profile: UserProfile,
        policies: list[PushPolicyConfig],
    ) -> PushPolicyConfig | None:
        ordered_policies = sorted(
            policies,
            key=lambda policy: float(policy.conditions.get("min_priority_score", -1)),
            reverse=True,
        )

        for policy in ordered_policies:
            if self._policy_matches(policy, priority, rule_result, user_profile):
                return policy
        return None

    def _policy_matches(
        self,
        policy: PushPolicyConfig,
        priority: dict[str, Any],
        rule_result: RuleAnalysisResult,
        user_profile: UserProfile,
    ) -> bool:
        conditions = policy.conditions

        if "min_priority_score" in conditions and priority["priority_score"] < float(conditions["min_priority_score"]):
            return False
        if "max_priority_score" in conditions and priority["priority_score"] > float(conditions["max_priority_score"]):
            return False

        relevance_statuses = self._normalize_list(conditions.get("relevance_status"))
        if relevance_statuses and priority["relevance_status"] not in relevance_statuses:
            return False

        priority_levels = self._normalize_list(conditions.get("priority_levels"))
        if priority_levels and priority["priority_level"] not in priority_levels:
            return False

        if "action_required" in conditions and priority["action_required"] != bool(conditions["action_required"]):
            return False
        if "should_continue" in conditions and rule_result.should_continue != bool(conditions["should_continue"]):
            return False

        category_any = self._normalize_list(conditions.get("categories_any"))
        if category_any and not set(category_any).intersection(rule_result.candidate_categories):
            return False

        if conditions.get("digest_enabled_required") and not user_profile.notification_preference.digest_enabled:
            return False

        return True

    def _fallback_action(self, priority: dict[str, Any], user_profile: UserProfile) -> str:
        if priority["priority_level"] == "critical":
            return "push_now"
        if priority["priority_level"] == "high":
            return "push_high"
        if priority["priority_level"] == "medium" and user_profile.notification_preference.digest_enabled:
            return "digest"
        if priority["relevance_status"] == "relevant":
            return "archive"
        return "ignore"

    def _is_muted(self, rule_result: RuleAnalysisResult, user_profile: UserProfile) -> bool:
        muted = set(user_profile.notification_preference.muted_categories)
        return bool(muted.intersection(rule_result.candidate_categories))

    def _find_action_policy(
        self,
        action: str,
        policies: list[PushPolicyConfig],
    ) -> PushPolicyConfig | None:
        for policy in policies:
            if policy.action == action:
                return policy
        return None

    def _resolve_forced_action(
        self,
        user_profile: UserProfile,
        decision_context: dict[str, Any] | None,
    ) -> str | None:
        force_action = (decision_context or {}).get("force_action")
        if force_action == "digest_or_archive":
            return "digest" if user_profile.notification_preference.digest_enabled else "archive"
        if isinstance(force_action, str) and force_action:
            return force_action
        return None

    def _normalize_list(self, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]
