from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

CampusAuthMode = Literal["cli_cas", "browser_cookie_import"]


class CampusAuthRequest(BaseModel):
    school_code: str = "szu"
    auth_mode: CampusAuthMode = "cli_cas"
    target_system: str
    entry_url: str
    username: str | None = None
    password: str | None = None
    username_env: str | None = None
    password_env: str | None = None
    imported_cookies: list[dict[str, Any]] = Field(default_factory=list)
    hints: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class CampusSessionHandle:
    school_code: str
    auth_mode: str
    target_system: str
    session: Any
    entry_url: str
    authenticated_url: str
    metadata: dict[str, Any] = field(default_factory=dict)
