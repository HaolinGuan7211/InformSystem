from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from backend.app.services.user_profile.models import ProfileContext, UserProfile


class ProfileContextSelector:
    def __init__(
        self,
        timezone_offset: str = "+08:00",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._timezone = self._parse_timezone(timezone_offset)
        self._now_provider = now_provider or (lambda: datetime.now(self._timezone))

    async def select(
        self,
        profile: UserProfile,
        required_facets: list[str],
        context: dict[str, Any] | None = None,
    ) -> ProfileContext:
        context = context or {}
        selected_facets = self._normalize_facets(required_facets)
        metadata: dict[str, Any] = {
            "selector_version": "v1",
        }

        if not selected_facets:
            selected_facets = self._infer_default_facets(profile)
            metadata["fallback_reason"] = "missing_required_profile_facets"

        payload: dict[str, Any] = {}
        unknown_facets: list[str] = []
        for facet in selected_facets:
            selected_payload = self._select_facet_payload(profile, facet)
            if selected_payload is None:
                unknown_facets.append(facet)
                continue
            payload[facet] = selected_payload

        if unknown_facets:
            metadata["unknown_facets"] = unknown_facets

        if not payload:
            fallback_facets = self._infer_default_facets(profile)
            for facet in fallback_facets:
                selected_payload = self._select_facet_payload(profile, facet)
                if selected_payload is not None:
                    payload[facet] = selected_payload
            selected_facets = fallback_facets
            metadata["fallback_reason"] = "no_supported_facets_selected"

        return ProfileContext(
            user_id=profile.user_id,
            facets=selected_facets,
            payload=payload,
            metadata=metadata,
            generated_at=str(context.get("generated_at", self._now_provider().isoformat())),
        )

    def _select_facet_payload(
        self,
        profile: UserProfile,
        facet: str,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        if facet == "identity_core":
            return {
                "name": profile.name,
                "student_id": profile.student_id,
                "college": profile.college,
                "major": profile.major,
                "grade": profile.grade,
                "degree_level": profile.degree_level,
                "identity_tags": list(profile.identity_tags),
            }
        if facet == "current_courses":
            return [
                {
                    "course_id": course.course_id,
                    "course_name": course.course_name,
                }
                for course in profile.enrolled_courses
            ]
        if facet == "academic_completion":
            return self._select_academic_completion_payload(profile.credit_status)
        if facet == "graduation_progress":
            return {
                "graduation_stage": profile.graduation_stage,
                "current_tasks": list(profile.current_tasks),
            }
        if facet == "activity_based_credit_gap":
            return self._select_attention_facet(
                profile.credit_status,
                signal_type="activity_based_credit_gap",
                attention_tag="activity_based",
                item_type="activity_credit_opportunity",
                keywords=("创新", "创业", "活动", "讲座", "思政", "activity"),
            )
        if facet == "online_platform_credit_gap":
            return self._select_attention_facet(
                profile.credit_status,
                signal_type="online_platform_credit_gap",
                attention_tag="online_platform",
                item_type="online_platform_course",
                keywords=("网课", "慕课", "平台", "online", "platform", "mooc"),
            )
        if facet == "custom_watch_items":
            return {
                "current_tasks": list(profile.current_tasks),
                "watch_items": list(profile.metadata.get("custom_watch_items", [])),
            }
        if facet == "notification_preference":
            return profile.notification_preference.model_dump()
        return None

    @staticmethod
    def _normalize_facets(required_facets: list[str]) -> list[str]:
        normalized: list[str] = []
        for facet in required_facets:
            cleaned = str(facet).strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @staticmethod
    def _infer_default_facets(profile: UserProfile) -> list[str]:
        facets = ["identity_core"]
        if profile.graduation_stage or profile.current_tasks:
            facets.append("graduation_progress")
        return facets

    def _select_academic_completion_payload(self, credit_status: dict[str, Any]) -> dict[str, Any]:
        return {
            "program_summary": credit_status.get("program_summary", {}),
            "module_progress": self._prioritize_module_progress(credit_status.get("module_progress", []), limit=8),
            "pending_items": self._limit_items(credit_status.get("pending_items", []), limit=12),
            "attention_signals": self._limit_items(credit_status.get("attention_signals", []), limit=8),
            "source_snapshot": credit_status.get("source_snapshot", {}),
        }

    def _select_attention_facet(
        self,
        credit_status: dict[str, Any],
        *,
        signal_type: str,
        attention_tag: str,
        item_type: str,
        keywords: tuple[str, ...],
    ) -> dict[str, Any]:
        module_progress = self._filter_module_progress(
            credit_status.get("module_progress", []),
            attention_tag=attention_tag,
            keywords=keywords,
        )
        module_ids = {
            str(module.get("module_id"))
            for module in module_progress
            if isinstance(module, dict) and module.get("module_id") is not None
        }
        pending_items = self._filter_pending_items(
            credit_status.get("pending_items", []),
            module_ids=module_ids,
            item_type=item_type,
            keywords=keywords,
        )
        attention_signals = self._filter_attention_signals(
            credit_status.get("attention_signals", []),
            signal_type=signal_type,
            keywords=keywords,
        )
        return {
            "module_progress": module_progress,
            "pending_items": pending_items,
            "attention_signals": attention_signals,
        }

    def _prioritize_module_progress(self, value: Any, limit: int) -> list[Any]:
        if not isinstance(value, list):
            return []

        child_incomplete: list[dict[str, Any]] = []
        child_completed: list[dict[str, Any]] = []
        parent_modules: dict[str, dict[str, Any]] = {}

        for item in value:
            if not isinstance(item, dict):
                continue
            module_level = item.get("module_level")
            completion_status = item.get("completion_status")
            if module_level == "parent":
                module_id = item.get("module_id")
                if module_id is not None:
                    parent_modules[str(module_id)] = item
                continue
            if completion_status == "completed":
                child_completed.append(item)
            else:
                child_incomplete.append(item)

        prioritized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for child in child_incomplete:
            parent_id = child.get("parent_module_id")
            if parent_id is not None:
                parent = parent_modules.get(str(parent_id))
                if parent is not None:
                    self._append_unique_module(prioritized, seen_ids, parent)
            self._append_unique_module(prioritized, seen_ids, child)

        for child in child_completed:
            if len(prioritized) >= limit:
                break
            self._append_unique_module(prioritized, seen_ids, child)

        if not prioritized:
            for item in value:
                if not isinstance(item, dict):
                    continue
                self._append_unique_module(prioritized, seen_ids, item)
                if len(prioritized) >= limit:
                    break

        return prioritized[:limit]

    def _filter_module_progress(
        self,
        value: Any,
        *,
        attention_tag: str,
        keywords: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []

        selected: list[dict[str, Any]] = []
        parent_ids: set[str] = set()

        for item in value:
            if not isinstance(item, dict):
                continue
            tags = set(item.get("attention_tags", []))
            text = f"{item.get('parent_module_name') or ''} {item.get('module_name') or ''}".lower()
            if attention_tag in tags or any(keyword.lower() in text for keyword in keywords):
                selected.append(item)
                parent_id = item.get("parent_module_id")
                if parent_id is not None:
                    parent_ids.add(str(parent_id))

        for item in value:
            if not isinstance(item, dict):
                continue
            if item.get("module_level") == "parent" and str(item.get("module_id")) in parent_ids:
                selected.append(item)

        deduped: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in selected:
            self._append_unique_module(deduped, seen_ids, item)
        return deduped[:8]

    @staticmethod
    def _filter_pending_items(
        value: Any,
        *,
        module_ids: set[str],
        item_type: str,
        keywords: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        selected: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            if item.get("item_type") == item_type:
                selected.append(item)
                continue
            module_id = item.get("module_id")
            if module_id is not None and str(module_id) in module_ids:
                selected.append(item)
                continue
            title = str(item.get("title", "")).lower()
            if any(keyword.lower() in title for keyword in keywords):
                selected.append(item)
        return selected[:12]

    @staticmethod
    def _filter_attention_signals(
        value: Any,
        *,
        signal_type: str,
        keywords: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        selected: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            if item.get("signal_type") == signal_type:
                selected.append(item)
                continue
            signal_key = str(item.get("signal_key", "")).lower()
            evidence = " ".join(str(entry) for entry in item.get("evidence", []))
            combined = f"{signal_key} {evidence}".lower()
            if any(keyword.lower() in combined for keyword in keywords):
                selected.append(item)
        return selected[:8]

    @staticmethod
    def _append_unique_module(target: list[dict[str, Any]], seen_ids: set[str], module: dict[str, Any]) -> None:
        module_id = module.get("module_id")
        key = str(module_id) if module_id is not None else repr(module)
        if key in seen_ids:
            return
        seen_ids.add(key)
        target.append(module)

    @staticmethod
    def _limit_items(value: Any, limit: int) -> list[Any]:
        if not isinstance(value, list):
            return []
        return value[:limit]

    @staticmethod
    def _parse_timezone(value: str) -> timezone:
        sign = -1 if value.startswith("-") else 1
        normalized = value[1:] if value[:1] in {"+", "-"} else value
        hours_text, minutes_text = normalized.split(":", maxsplit=1)
        offset = timedelta(hours=int(hours_text), minutes=int(minutes_text))
        return timezone(sign * offset)
