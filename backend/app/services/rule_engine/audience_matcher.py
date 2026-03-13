from __future__ import annotations

import re
from typing import Any

from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.user_profile.models import UserProfile

COLLEGE_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z]{2,20}学院")
GRADE_PATTERN = re.compile(r"(20\d{2})(?:级|届)")
DEGREE_TO_GRAD_YEARS = {
    "undergraduate": 4,
    "master": 3,
    "graduate": 3,
    "doctoral": 4,
    "phd": 4,
}


class AudienceMatcher:
    def __init__(self, thresholds: dict[str, Any] | None = None) -> None:
        self._thresholds = thresholds or {}

    async def match(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        signals: dict[str, Any],
        evaluated_rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        content_view = signals["content_view"]
        explanations: list[str] = []
        matched_rules = []
        candidate_categories: list[str] = []
        audience_values = list(signals.get("explicit_audience") or signals.get("audience", []))

        score = self._source_bonus(event)
        profile_match = False
        explicit_audience = bool(audience_values)

        for match in evaluated_rules:
            outputs = match["rule"].outputs
            if outputs.get("dimension") != "audience":
                continue

            profile_match = True
            score += float(outputs.get("weight", 0.0))
            self._extend_unique(candidate_categories, outputs.get("candidate_categories", []))
            explanation = outputs.get("explanation")
            if explanation:
                explanations.append(explanation)

            if outputs.get("emit_match", True):
                matched_rules.append(match["matched_rule"])

        direct_profile_score = 0.0
        direct_explanations: list[str] = []
        direct_profile_match = False
        explicit_profile_mismatch = False
        if not explicit_audience:
            direct_profile_score, direct_explanations, direct_profile_match, explicit_profile_mismatch = (
                self._match_profile_context(content_view, user_profile)
            )
            score += direct_profile_score
            profile_match = profile_match or direct_profile_match
            explanations.extend(direct_explanations)

        for match in evaluated_rules:
            outputs = match["rule"].outputs
            if outputs.get("dimension") == "audience":
                continue
            if explicit_audience and not profile_match:
                continue
            score += float(outputs.get("weight", 0.0))
            self._extend_unique(candidate_categories, outputs.get("candidate_categories", []))
            explanation = outputs.get("explanation")
            if explanation:
                explanations.append(explanation)
            if outputs.get("emit_match", True):
                matched_rules.append(match["matched_rule"])

        score = round(min(score, 1.0), 2)
        relevant_threshold = float(self._thresholds.get("relevant_score", 0.7))
        unknown_threshold = float(self._thresholds.get("unknown_score", 0.35))

        if explicit_audience and not profile_match:
            relevance_status = "irrelevant"
            score = min(score, 0.2)
        elif explicit_profile_mismatch and not profile_match:
            relevance_status = "irrelevant"
            score = min(score, 0.2)
        elif profile_match and score >= relevant_threshold:
            relevance_status = "relevant"
        elif score >= relevant_threshold and not explicit_audience:
            relevance_status = "relevant"
        elif score >= unknown_threshold:
            relevance_status = "unknown"
        else:
            relevance_status = "irrelevant" if explicit_audience else "unknown"

        return {
            "relevance_status": relevance_status,
            "relevance_score": round(score, 2),
            "matched_rules": self._dedupe_rules(matched_rules),
            "candidate_categories": candidate_categories,
            "explanations": self._dedupe_strings(explanations),
            "profile_match": profile_match,
        }

    def _match_profile_context(
        self,
        content_view: str,
        user_profile: UserProfile,
    ) -> tuple[float, list[str], bool, bool]:
        score = 0.0
        explanations: list[str] = []
        profile_match = False
        explicit_mismatch = False

        colleges = set(COLLEGE_PATTERN.findall(content_view))
        if colleges and user_profile.college:
            if user_profile.college in colleges:
                score += 0.35
                profile_match = True
                explanations.append("命中学院范围")
            else:
                explicit_mismatch = True

        if user_profile.major and user_profile.major in content_view:
            score += 0.25
            profile_match = True
            explanations.append("命中专业范围")

        expected_grad_year = self._expected_graduation_year(user_profile)
        for year in GRADE_PATTERN.findall(content_view):
            if user_profile.grade and year == user_profile.grade:
                score += 0.25
                profile_match = True
                explanations.append("命中年级范围")
                break
            if expected_grad_year and year == expected_grad_year:
                score += 0.2
                profile_match = True
                explanations.append("命中届别范围")
                break

        for course in user_profile.enrolled_courses:
            if course.course_name and course.course_name in content_view:
                score += 0.35
                profile_match = True
                explanations.append("命中当前选课范围")
                break

        for task in user_profile.current_tasks:
            if task and task in content_view:
                score += 0.1
                profile_match = True
                explanations.append("命中当前待办状态")
                break

        return score, self._dedupe_strings(explanations), profile_match, explicit_mismatch

    def _expected_graduation_year(self, user_profile: UserProfile) -> str | None:
        if not user_profile.grade or not user_profile.grade.isdigit():
            return None
        years = DEGREE_TO_GRAD_YEARS.get((user_profile.degree_level or "").lower())
        if years is None:
            return None
        return str(int(user_profile.grade) + years)

    def _source_bonus(self, event: SourceEvent) -> float:
        authority = event.metadata.get("authority_level")
        if authority == "high" or event.source_type in {"wecom", "website"}:
            return float(self._thresholds.get("source_bonus_high", 0.1))
        if authority == "medium" or event.source_type == "manual":
            return float(self._thresholds.get("source_bonus_medium", 0.05))
        return float(self._thresholds.get("source_bonus_low", 0.0))

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
