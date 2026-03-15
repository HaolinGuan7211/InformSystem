from __future__ import annotations

import re
from typing import Any

from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.user_profile.models import UserProfile

COLLEGE_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z]{2,20}学院")
MAJOR_PATTERN = re.compile(r"([\u4e00-\u9fffA-Za-z]{2,20})(?:专业|方向)")
GRADE_PATTERN = re.compile(r"(20\d{2})(?:级|届)")
COURSE_TITLE_PATTERN = re.compile(r"《([^》]{2,40})》")
DEGREE_TO_GRAD_YEARS = {
    "undergraduate": 4,
    "master": 3,
    "graduate": 3,
    "doctoral": 4,
    "phd": 4,
}
EXPLICIT_AUDIENCE_PREFIXES = ("仅限", "仅面向", "面向", "针对", "适用于", "限", "请")
EXPLICIT_AUDIENCE_SUFFIXES = ("学生", "同学", "毕业生", "本科生", "研究生", "硕士生", "博士生")
IDENTITY_KEYWORDS = ("毕业生", "本科生", "研究生", "硕士生", "博士生")
COURSE_NOTICE_KEYWORDS = ("课程", "调课", "停课", "补课", "考试", "上课", "选课", "课堂", "作业", "考核")
RESTRICTIVE_COURSE_KEYWORDS = ("停课", "调课", "补课", "考试", "考核", "作业", "签到", "已选", "已修", "选课同学", "已选课")
OPEN_OPPORTUNITY_KEYWORDS = (
    "创新创业短课",
    "短课",
    "通识课",
    "公开课",
    "开放课",
    "研习营",
    "夏令营",
    "讲座",
    "工作坊",
    "展示活动",
)
OPEN_COURSE_OPPORTUNITY_HINTS = ("上线", "开放", "公开", "报名", "申请", "欢迎", "感兴趣")
IDENTITY_RESTRICTION_HINTS = ("通知", "提醒", "材料", "提交", "审核", "办理", "申请", "报名", "名单", "资格", "手续")
BROAD_AUDIENCE_VALUES = {"student", "students", "学生", "同学"}


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
        normalized_audience_values = self._normalize_audience_values(audience_values)

        score = self._source_bonus(event)
        direct_profile = self._match_profile_context(
            content_view,
            user_profile,
            suppress_explicit_score=bool(audience_values),
        )
        score += direct_profile["score"]
        explanations.extend(direct_profile["explanations"])

        profile_match = bool(direct_profile["profile_match"])
        hard_match = bool(direct_profile["hard_match"])
        hard_mismatch = bool(direct_profile["hard_mismatch"])
        explicit_audience = bool(direct_profile["has_explicit_audience"] or audience_values)
        audience_rule_match = False
        hard_audience_rule_match = False

        for match in evaluated_rules:
            outputs = match["rule"].outputs
            if outputs.get("dimension") != "audience":
                continue

            audience_rule_match = True
            profile_match = True
            score += float(outputs.get("weight", 0.0))
            self._extend_unique(candidate_categories, outputs.get("candidate_categories", []))
            explanation = outputs.get("explanation")
            if explanation:
                explanations.append(explanation)
            if self._is_hard_audience_rule(match["rule"].conditions):
                hard_match = True
                hard_audience_rule_match = True

            if outputs.get("emit_match", True):
                matched_rules.append(match["matched_rule"])

        for match in evaluated_rules:
            outputs = match["rule"].outputs
            if outputs.get("dimension") == "audience":
                continue
            if hard_mismatch or (explicit_audience and not profile_match):
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
        candidate_threshold = float(self._thresholds.get("unknown_score", 0.35))

        if hard_mismatch or (explicit_audience and not profile_match):
            relevance_status = "irrelevant"
            score = min(score, 0.2)
        elif hard_match and score >= candidate_threshold:
            relevance_status = "relevant"
        elif (
            audience_rule_match
            and explicit_audience
            and score >= relevant_threshold
            and not self._is_broad_audience_only(normalized_audience_values)
            and (hard_audience_rule_match or direct_profile["has_explicit_audience"])
        ):
            relevance_status = "relevant"
        elif score >= candidate_threshold:
            relevance_status = "unknown"
        else:
            relevance_status = "unknown"

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
        suppress_explicit_score: bool = False,
    ) -> dict[str, Any]:
        score = 0.0
        explanations: list[str] = []
        profile_match = False
        hard_match = False
        hard_mismatch = False
        has_explicit_audience = False

        explicit_identities = self._extract_explicit_identities(content_view)
        if explicit_identities:
            has_explicit_audience = True
            if any(self._identity_matches(identity, user_profile) for identity in explicit_identities):
                if not suppress_explicit_score:
                    score += 0.35
                    explanations.append("命中明确身份范围")
                profile_match = True
                hard_match = True
            else:
                hard_mismatch = True
                explanations.append("明确身份范围与当前用户不匹配")

        explicit_colleges = self._extract_explicit_colleges(content_view)
        if explicit_colleges:
            has_explicit_audience = True
            if user_profile.college and user_profile.college in explicit_colleges:
                if not suppress_explicit_score:
                    score += 0.3
                    explanations.append("命中明确学院范围")
                profile_match = True
                hard_match = True
            else:
                hard_mismatch = True
                explanations.append("明确学院范围与当前用户不匹配")

        explicit_majors = self._extract_explicit_majors(content_view)
        if explicit_majors:
            has_explicit_audience = True
            if user_profile.major and user_profile.major in explicit_majors:
                if not suppress_explicit_score:
                    score += 0.25
                    explanations.append("命中明确专业范围")
                profile_match = True
                hard_match = True
            else:
                hard_mismatch = True
                explanations.append("明确专业范围与当前用户不匹配")

        explicit_years = self._extract_explicit_years(content_view)
        if explicit_years:
            has_explicit_audience = True
            expected_grad_year = self._expected_graduation_year(user_profile)
            matched_year = False
            for year in explicit_years:
                if user_profile.grade and year == user_profile.grade:
                    if not suppress_explicit_score:
                        score += 0.25
                        explanations.append("命中明确年级范围")
                    profile_match = True
                    hard_match = True
                    matched_year = True
                    break
                if expected_grad_year and year == expected_grad_year:
                    if not suppress_explicit_score:
                        score += 0.2
                        explanations.append("命中明确届别范围")
                    profile_match = True
                    hard_match = True
                    matched_year = True
                    break
            if not matched_year:
                hard_mismatch = True
                explanations.append("明确年级范围与当前用户不匹配")

        for course in user_profile.enrolled_courses:
            if course.course_name and course.course_name in content_view:
                if not suppress_explicit_score:
                    score += 0.4
                    explanations.append("命中明确课程范围")
                profile_match = True
                hard_match = True
                has_explicit_audience = True
                break
        else:
            explicit_courses = self._extract_explicit_course_titles(content_view)
            if explicit_courses:
                has_explicit_audience = True
                hard_mismatch = True
                explanations.append("明确课程范围与当前用户不匹配")

        for task in user_profile.current_tasks:
            if task and task in content_view:
                if not suppress_explicit_score:
                    score += 0.1
                    explanations.append("命中当前待办状态")
                profile_match = True
                break

        return {
            "score": score,
            "explanations": self._dedupe_strings(explanations),
            "profile_match": profile_match,
            "hard_match": hard_match,
            "hard_mismatch": hard_mismatch,
            "has_explicit_audience": has_explicit_audience,
        }

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

    def _extract_explicit_identities(self, content_view: str) -> list[str]:
        values: list[str] = []
        for identity in IDENTITY_KEYWORDS:
            if self._has_explicit_identity_target(content_view, identity):
                values.append(identity)
        return values

    def _extract_explicit_colleges(self, content_view: str) -> list[str]:
        values: list[str] = []
        for college in set(COLLEGE_PATTERN.findall(content_view)):
            if self._has_explicit_target(content_view, college):
                values.append(college)
        return values

    def _extract_explicit_majors(self, content_view: str) -> list[str]:
        values: list[str] = []
        for major in {match.group(1) for match in MAJOR_PATTERN.finditer(content_view)}:
            if self._has_explicit_target(content_view, f"{major}专业") or self._has_explicit_target(content_view, f"{major}方向"):
                values.append(major)
        return values

    def _extract_explicit_years(self, content_view: str) -> list[str]:
        values: list[str] = []
        for year in set(GRADE_PATTERN.findall(content_view)):
            if self._has_explicit_year_target(content_view, year):
                values.append(year)
        return values

    def _extract_explicit_course_titles(self, content_view: str) -> list[str]:
        if not self._looks_like_course_notice(content_view):
            return []
        if self._is_open_course_opportunity(content_view):
            return []

        titles: list[str] = []
        for title in COURSE_TITLE_PATTERN.findall(content_view):
            if title and self._has_explicit_course_restriction(content_view, title):
                titles.append(title)
        return titles

    def _has_explicit_target(self, content_view: str, target: str) -> bool:
        escaped = re.escape(target)
        prefix_pattern = rf"(?:{'|'.join(EXPLICIT_AUDIENCE_PREFIXES)})\s*{escaped}"
        suffix_pattern = rf"{escaped}(?:全体)?(?:{'|'.join(EXPLICIT_AUDIENCE_SUFFIXES)})"
        return bool(re.search(prefix_pattern, content_view) or re.search(suffix_pattern, content_view))

    def _has_explicit_year_target(self, content_view: str, year: str) -> bool:
        escaped = re.escape(year)
        prefix_pattern = rf"(?:{'|'.join(EXPLICIT_AUDIENCE_PREFIXES)})\s*{escaped}(?:级|届)"
        suffix_pattern = rf"{escaped}(?:级|届)(?:{'|'.join(EXPLICIT_AUDIENCE_SUFFIXES)})"
        return bool(re.search(prefix_pattern, content_view) or re.search(suffix_pattern, content_view))

    def _has_explicit_identity_target(self, content_view: str, identity: str) -> bool:
        escaped = re.escape(identity)
        prefix_pattern = rf"(?:{'|'.join(EXPLICIT_AUDIENCE_PREFIXES)})\s*(?:20\d{{2}}(?:级|届))?\s*{escaped}"
        year_prefix_pattern = rf"20\d{{2}}(?:级|届)\s*{escaped}"
        context_pattern = rf"{escaped}(?:[^。\n，,；;]{{0,12}})(?:{'|'.join(IDENTITY_RESTRICTION_HINTS)})"
        return bool(
            re.search(prefix_pattern, content_view)
            or re.search(year_prefix_pattern, content_view)
            or re.search(context_pattern, content_view)
        )

    def _looks_like_course_notice(self, content_view: str) -> bool:
        return any(keyword in content_view for keyword in COURSE_NOTICE_KEYWORDS)

    def _is_open_course_opportunity(self, content_view: str) -> bool:
        if not any(keyword in content_view for keyword in OPEN_OPPORTUNITY_KEYWORDS):
            return False
        return any(keyword in content_view for keyword in OPEN_COURSE_OPPORTUNITY_HINTS)

    def _has_explicit_course_restriction(self, content_view: str, title: str) -> bool:
        escaped = re.escape(title)
        selected_patterns = (
            rf"已选(?:修|课)?《{escaped}》",
            rf"选(?:修|课)《{escaped}》的(?:同学|学生)",
            rf"《{escaped}》(?:课程)?(?:{'|'.join(RESTRICTIVE_COURSE_KEYWORDS)})",
            rf"《{escaped}》[^。\n]{{0,12}}(?:选课同学|已选课同学|已修同学)",
        )
        return any(re.search(pattern, content_view) for pattern in selected_patterns)

    def _identity_matches(self, identity: str, user_profile: UserProfile) -> bool:
        if identity in user_profile.identity_tags:
            return True
        degree_level = (user_profile.degree_level or "").lower()
        if identity == "毕业生":
            return bool(user_profile.graduation_stage)
        if identity == "本科生":
            return degree_level == "undergraduate"
        if identity in {"研究生", "硕士生"}:
            return degree_level in {"graduate", "master"}
        if identity == "博士生":
            return degree_level in {"doctoral", "phd"}
        return False

    def _is_hard_audience_rule(self, conditions: dict[str, Any]) -> bool:
        profile_any = conditions.get("profile_any", {})
        hard_fields = {"identity_tags", "graduation_stage", "college", "major", "grade", "enrolled_courses"}
        return any(field_name in hard_fields for field_name in profile_any)

    def _normalize_audience_values(self, values: list[Any]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            cleaned = str(value).strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    def _is_broad_audience_only(self, values: list[str]) -> bool:
        if not values:
            return False
        return all(value in BROAD_AUDIENCE_VALUES for value in values)

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
