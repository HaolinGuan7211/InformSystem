from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CourseInfo(BaseModel):
    course_id: str
    course_name: str
    teacher: str | None = None
    semester: str | None = None


class NotificationPreference(BaseModel):
    channels: list[str] = Field(default_factory=list)
    quiet_hours: list[str] = Field(default_factory=list)
    digest_enabled: bool = True
    muted_categories: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    user_id: str
    student_id: str
    name: str | None = None
    college: str | None = None
    major: str | None = None
    grade: str | None = None
    degree_level: str | None = None
    identity_tags: list[str] = Field(default_factory=list)
    graduation_stage: str | None = None
    enrolled_courses: list[CourseInfo] = Field(default_factory=list)
    credit_status: dict[str, Any] = Field(default_factory=dict)
    current_tasks: list[str] = Field(default_factory=list)
    notification_preference: NotificationPreference = Field(default_factory=NotificationPreference)
    metadata: dict[str, Any] = Field(default_factory=dict)
