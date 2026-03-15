from __future__ import annotations

from typing import Any

from backend.app.shared.models import AIAnalysisResult, RuleAnalysisResult, SourceEvent, UserProfile


class ProfileSignalResolver:
    _attention_bonus_by_severity = {
        "critical": 12.0,
        "high": 10.0,
        "medium": 6.0,
        "low": 3.0,
    }
    _pending_bonus_by_priority = {
        "critical": 8.0,
        "high": 8.0,
        "medium": 5.0,
        "low": 2.0,
    }
    _category_keywords = {
        "credit": ["学分", "补修", "模块", "缺口", "credit"],
        "graduation": ["毕业", "离校", "答辩"],
        "material_submission": ["材料", "提交", "审核"],
        "course_schedule_change": ["课程", "调课", "安排"],
        "exam": ["考试", "补考", "缓考"],
    }

    async def evaluate(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
    ) -> dict[str, Any]:
        credit_status = user_profile.credit_status or {}
        attention_signals = self._ensure_list(credit_status.get("attention_signals"))
        pending_items = self._ensure_list(credit_status.get("pending_items"))
        explicit_signal_keys = set(self._ensure_list(rule_result.extracted_signals.get("attention_signal_keys")))
        explicit_pending_ids = set(self._ensure_list(rule_result.extracted_signals.get("pending_item_ids")))
        normalized_text = self._build_normalized_text(event, rule_result, ai_result)

        matched_attention = [
            signal
            for signal in attention_signals
            if self._matches_attention_signal(
                signal=signal,
                explicit_signal_keys=explicit_signal_keys,
                normalized_text=normalized_text,
                categories=rule_result.candidate_categories,
            )
        ]
        matched_pending = [
            item
            for item in pending_items
            if self._matches_pending_item(
                item=item,
                explicit_pending_ids=explicit_pending_ids,
                normalized_text=normalized_text,
                categories=rule_result.candidate_categories,
            )
        ]

        score_bonus = 0.0
        if matched_attention:
            score_bonus += max(self._attention_bonus(signal) for signal in matched_attention)
        if matched_pending:
            score_bonus += max(self._pending_bonus(item) for item in matched_pending)
        if matched_attention and matched_pending:
            score_bonus += 2.0

        return {
            "matched_attention_signals": matched_attention,
            "matched_pending_items": matched_pending,
            "score_bonus": min(score_bonus, 20.0),
        }

    def _matches_attention_signal(
        self,
        signal: dict[str, Any],
        explicit_signal_keys: set[str],
        normalized_text: str,
        categories: list[str],
    ) -> bool:
        signal_key = str(signal.get("signal_key") or "").strip()
        if signal_key and signal_key in explicit_signal_keys:
            return True

        signal_text = self._join_text(
            signal.get("signal_type"),
            signal.get("signal_key"),
            signal.get("signal_value"),
            *self._ensure_list(signal.get("evidence")),
        )
        if signal_text and signal_text in normalized_text:
            return True

        return self._category_overlap(categories, self._join_text(signal_text))

    def _matches_pending_item(
        self,
        item: dict[str, Any],
        explicit_pending_ids: set[str],
        normalized_text: str,
        categories: list[str],
    ) -> bool:
        status = str(item.get("status") or "unknown")
        if status not in {"pending", "unknown"}:
            return False

        item_id = str(item.get("item_id") or "").strip()
        if item_id and item_id in explicit_pending_ids:
            return True

        item_text = self._join_text(
            item.get("item_type"),
            item.get("title"),
            item.get("module_name"),
            item.get("priority_hint"),
        )
        if item_text and item_text in normalized_text:
            return True

        return self._category_overlap(categories, item_text)

    def _build_normalized_text(
        self,
        event: SourceEvent,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
    ) -> str:
        return self._join_text(
            event.title,
            event.content_text,
            ai_result.normalized_category if ai_result else None,
            ai_result.summary if ai_result else None,
            *rule_result.candidate_categories,
            *rule_result.explanation,
            *self._flatten_values(rule_result.extracted_signals),
        )

    def _category_overlap(self, categories: list[str], candidate_text: str) -> bool:
        if not candidate_text:
            return False

        for category in categories:
            for keyword in self._category_keywords.get(category, []):
                if keyword and keyword in candidate_text:
                    return True
        return False

    def _attention_bonus(self, signal: dict[str, Any]) -> float:
        severity = str(signal.get("severity") or "low")
        return self._attention_bonus_by_severity.get(severity, 3.0)

    def _pending_bonus(self, item: dict[str, Any]) -> float:
        priority_hint = str(item.get("priority_hint") or "medium")
        return self._pending_bonus_by_priority.get(priority_hint, 3.0)

    def _flatten_values(self, payload: Any) -> list[str]:
        values: list[str] = []
        if payload is None:
            return values
        if isinstance(payload, dict):
            for value in payload.values():
                values.extend(self._flatten_values(value))
            return values
        if isinstance(payload, list):
            for item in payload:
                values.extend(self._flatten_values(item))
            return values
        if isinstance(payload, (str, int, float)):
            values.append(str(payload))
        return values

    def _join_text(self, *parts: Any) -> str:
        normalized_parts = [str(part).strip().lower() for part in parts if part not in (None, "", [])]
        return " ".join(part for part in normalized_parts if part)

    def _ensure_list(self, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]
