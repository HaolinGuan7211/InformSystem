from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field

from backend.app.services.user_profile.models import UserProfile


class LightProfileTags(BaseModel):
    user_id: str
    college: str | None = None
    major: str | None = None
    grade: str | None = None
    degree_level: str | None = None
    identity_tags: list[str] = Field(default_factory=list)
    graduation_tags: list[str] = Field(default_factory=list)
    current_course_tags: list[str] = Field(default_factory=list)
    current_task_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str


class LightProfileTagBuilder:
    def __init__(
        self,
        timezone_offset: str = "+08:00",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._timezone = self._parse_timezone(timezone_offset)
        self._now_provider = now_provider or (lambda: datetime.now(self._timezone))

    async def build(
        self,
        profile: UserProfile,
        context: dict[str, Any] | None = None,
    ) -> LightProfileTags:
        context = context or {}
        return LightProfileTags(
            user_id=profile.user_id,
            college=profile.college,
            major=profile.major,
            grade=profile.grade,
            degree_level=profile.degree_level,
            identity_tags=self._normalize_tags(profile.identity_tags),
            graduation_tags=self._collect_graduation_tags(profile),
            current_course_tags=self._collect_course_tags(profile),
            current_task_tags=self._collect_task_tags(profile),
            metadata={
                "builder_version": "v1",
                "source": "user_profile",
                "included_fields": [
                    "college",
                    "major",
                    "grade",
                    "degree_level",
                    "identity_tags",
                    "graduation_tags",
                    "current_course_tags",
                    "current_task_tags",
                ],
                "excluded_heavy_fields": [
                    "credit_status",
                    "full_current_tasks",
                    "notification_preference",
                ],
            },
            generated_at=str(context.get("generated_at", self._now_provider().isoformat())),
        )

    @staticmethod
    def _normalize_tags(value: list[str]) -> list[str]:
        tags: list[str] = []
        for item in value:
            cleaned = str(item).strip()
            if cleaned and cleaned not in tags:
                tags.append(cleaned)
        return tags

    def _collect_course_tags(self, profile: UserProfile) -> list[str]:
        tags: list[str] = []
        for course in profile.enrolled_courses:
            cleaned = str(course.course_name).strip()
            if cleaned and cleaned not in tags:
                tags.append(cleaned)
            if len(tags) >= 8:
                break
        return tags

    def _collect_graduation_tags(self, profile: UserProfile) -> list[str]:
        tags: list[str] = []
        graduation_stage = str(profile.graduation_stage or "").strip()
        if not graduation_stage:
            return tags

        tags.append(graduation_stage)
        if self._is_graduation_related_stage(graduation_stage):
            tags.append("graduating_student")
        return tags

    def _collect_task_tags(self, profile: UserProfile) -> list[str]:
        tags: list[str] = []
        for task in profile.current_tasks:
            cleaned = str(task).strip()
            if cleaned and cleaned not in tags:
                tags.append(cleaned)
            if len(tags) >= 8:
                break
        return tags

    @staticmethod
    def _is_graduation_related_stage(value: str) -> bool:
        normalized = value.strip().lower()
        return any(
            keyword in normalized
            for keyword in ("graduation", "graduate", "degree", "thesis", "defense", "离校", "毕业")
        )

    @staticmethod
    def _parse_timezone(value: str) -> timezone:
        sign = -1 if value.startswith("-") else 1
        normalized = value[1:] if value[:1] in {"+", "-"} else value
        hours_text, minutes_text = normalized.split(":", maxsplit=1)
        offset = timedelta(hours=int(hours_text), minutes=int(minutes_text))
        return timezone(sign * offset)
