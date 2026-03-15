from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.services.user_profile.models import UserProfile


class NormalizedProfileDraft(BaseModel):
    school_code: str
    profile: UserProfile
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failed_sources: list[str] = Field(default_factory=list)
    field_sources: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProfileSyncResult(BaseModel):
    school_code: str
    auth_mode: str
    persisted: bool
    profile: UserProfile
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failed_sources: list[str] = Field(default_factory=list)
    field_sources: dict[str, str] = Field(default_factory=dict)
    sampled_fragments: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
