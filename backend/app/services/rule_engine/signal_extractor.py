from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from backend.app.services.rule_engine.models import RuleConfig

DEFAULT_ACTION_KEYWORDS = (
    "提交",
    "报名",
    "确认",
    "缴费",
    "申请",
    "参加",
    "填报",
    "登记",
)
DEADLINE_PATTERN = re.compile(
    r"(?:(?P<year>\d{4})年)?(?P<month>\d{1,2})月(?P<day>\d{1,2})日(?P<suffix>前|日前|之前|截止|截止前|前完成|前提交|前报名)"
)


class SignalExtractor:
    async def extract(self, rule_view: dict[str, Any], rules: list[RuleConfig]) -> dict[str, Any]:
        content_view = rule_view["content_view"]
        rule_hits: dict[str, dict[str, Any]] = {}
        action_keywords = list(self._extract_action_keywords(content_view, rules))
        deadline_text, deadline_at = self._extract_deadline(content_view, rule_view["reference_time"])

        for rule in rules:
            conditions = rule.conditions
            matched_any = [
                keyword
                for keyword in conditions.get("any_keywords", [])
                if keyword and keyword in content_view
            ]
            matched_all = [
                keyword
                for keyword in conditions.get("all_keywords", [])
                if keyword and keyword in content_view
            ]
            regex_matches: list[str] = []
            for pattern in conditions.get("regex_patterns", []):
                regex_matches.extend(match for match in re.findall(pattern, content_view) if match)

            rule_hits[rule.rule_id] = {
                "matched_any": matched_any,
                "matched_all": matched_all,
                "regex_matches": regex_matches,
                "has_deadline": deadline_text is not None,
                "action_keywords": [
                    keyword
                    for keyword in conditions.get("action_keywords", [])
                    if keyword and keyword in content_view
                ],
            }

        return {
            "content_view": content_view,
            "context_view": rule_view["context_view"],
            "rule_hits": rule_hits,
            "action_keywords": action_keywords,
            "deadline_text": deadline_text,
            "deadline_at": deadline_at,
        }

    def _extract_action_keywords(self, content_view: str, rules: list[RuleConfig]) -> list[str]:
        ordered_keywords: list[str] = []
        seen: set[str] = set()

        for keyword in DEFAULT_ACTION_KEYWORDS:
            if keyword in content_view and keyword not in seen:
                ordered_keywords.append(keyword)
                seen.add(keyword)

        for rule in rules:
            for keyword in rule.conditions.get("action_keywords", []):
                if keyword in content_view and keyword not in seen:
                    ordered_keywords.append(keyword)
                    seen.add(keyword)

        return ordered_keywords

    def _extract_deadline(self, content_view: str, reference_time: str | None) -> tuple[str | None, str | None]:
        match = DEADLINE_PATTERN.search(content_view)
        if not match:
            return None, None

        deadline_text = match.group(0)
        year = int(match.group("year")) if match.group("year") else None
        month = int(match.group("month"))
        day = int(match.group("day"))
        deadline_at = self._to_deadline_timestamp(year, month, day, reference_time)
        return deadline_text, deadline_at

    def _to_deadline_timestamp(
        self,
        year: int | None,
        month: int,
        day: int,
        reference_time: str | None,
    ) -> str | None:
        if not reference_time:
            return None

        base_time = datetime.fromisoformat(reference_time)
        target_year = year or base_time.year
        if year is None and (month, day) < (base_time.month, base_time.day):
            target_year += 1

        deadline_at = datetime(
            year=target_year,
            month=month,
            day=day,
            hour=23,
            minute=59,
            second=59,
            tzinfo=base_time.tzinfo,
        )

        if deadline_at < base_time - timedelta(days=30):
            deadline_at = deadline_at.replace(year=deadline_at.year + 1)

        return deadline_at.isoformat()
