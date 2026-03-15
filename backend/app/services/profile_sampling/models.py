from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

AuthMode = Literal[
    "szu_http_cas",
    "szu_http_cas_ehall",
    "browser_cookie_import",
    "browser_cookie_import_ehall",
    "offline_fixture",
]


class ProfileSyncRequest(BaseModel):
    school_code: str = "szu"
    auth_mode: AuthMode = "szu_http_cas"
    persist: bool = True
    dry_run: bool = False
    user_id: str | None = None
    username: str | None = None
    password: str | None = None
    username_env: str | None = None
    password_env: str | None = None
    imported_cookies: list[dict[str, Any]] = Field(default_factory=list)
    hints: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class SchoolSessionHandle:
    school_code: str
    auth_mode: str
    session: Any
    entry_url: str
    authenticated_url: str
    metadata: dict[str, Any] = field(default_factory=dict)


class RawProfileFragment(BaseModel):
    fragment_type: str
    source_system: str
    payload: dict[str, Any] = Field(default_factory=dict)
    collected_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProfileSamplingResult(BaseModel):
    school_code: str
    auth_mode: str
    fragments: list[RawProfileFragment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failed_sources: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
