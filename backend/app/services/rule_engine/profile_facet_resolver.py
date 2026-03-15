from __future__ import annotations

from typing import Any

from backend.app.services.rule_engine.models import ProfileFacet

VALID_PROFILE_FACETS: set[str] = {
    "identity_core",
    "current_courses",
    "academic_completion",
    "graduation_progress",
    "activity_based_credit_gap",
    "online_platform_credit_gap",
    "custom_watch_items",
    "notification_preference",
}

FACET_HINTS_BY_CATEGORY: dict[str, list[ProfileFacet]] = {
    "graduation": ["identity_core", "graduation_progress"],
    "material_submission": ["identity_core"],
    "course_schedule": ["current_courses"],
    "course_notice": ["current_courses"],
    "credit_recognition": ["academic_completion"],
    "academic_completion": ["academic_completion"],
    "open_opportunity": ["identity_core"],
}


class ProfileFacetResolver:
    def resolve(
        self,
        *,
        signals: dict[str, Any],
        evaluated_rules: list[dict[str, Any]],
        candidate_categories: list[str],
    ) -> list[ProfileFacet]:
        facets: list[str] = []

        for match in evaluated_rules:
            self._extend_unique(facets, match["rule"].outputs.get("required_profile_facets", []))

        for category in candidate_categories:
            self._extend_unique(facets, FACET_HINTS_BY_CATEGORY.get(category, []))

        content_view = signals.get("content_view", "")
        audience_values = signals.get("audience", [])

        if audience_values:
            self._extend_unique(facets, ["identity_core"])
        if any(keyword in content_view for keyword in ("学分", "培养方案", "模块", "完成情况", "认定")):
            self._extend_unique(facets, ["academic_completion"])
        if any(keyword in content_view for keyword in ("毕业", "学位", "离校", "毕业审核")):
            self._extend_unique(facets, ["graduation_progress"])
        if any(keyword in content_view for keyword in ("课程", "调课", "停课", "补课")):
            self._extend_unique(facets, ["current_courses"])
        if any(keyword in content_view for keyword in ("活动学分", "第二课堂", "美育", "劳育", "社会实践")):
            self._extend_unique(facets, ["activity_based_credit_gap"])
        if any(keyword in content_view for keyword in ("网课", "在线学习", "慕课", "平台学分")):
            self._extend_unique(facets, ["online_platform_credit_gap"])
        if any(keyword in content_view for keyword in ("待办", "任务", "关注事项", "自定义提醒")):
            self._extend_unique(facets, ["custom_watch_items"])

        return [facet for facet in facets if facet in VALID_PROFILE_FACETS]

    def _extend_unique(self, target: list[str], values: list[str]) -> None:
        for value in values:
            if value not in target:
                target.append(value)
